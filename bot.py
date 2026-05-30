import os
import re
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from pdf_generator import generate_pdf
from database import db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────
BOT_TOKEN        = os.environ["BOT_TOKEN"]
GROUP_ID         = int(os.environ["GROUP_ID"])
MANAGER_PASSWORD = "Bullet"

INTERVIEWERS = {
    "ravi":     "Ravi Sir",
    "nikki":    "Nikki Ma'am",
    "amit":     "Amit Sir",
    "raksha":   "Raksha Ma'am",
}
MANAGER_KEY  = "shivangi"
MANAGER_NAME = "Shivangi Ma'am"

SECTIONS = [
    "Body Language", "Communication", "Skills & Functions",
    "Situational Handling Aptitude", "Stress Handling", "Team Work",
    "Presence of Mind", "Awareness", "Clarity of Thoughts", "Integrity",
]

STUDENT_CACHE_MINUTES = 20

# ── States ─────────────────────────────────────────────────────────
(
    ST_SELECT_INTERVIEWER,  # 0
    ST_STUDENT_NAME,        # 1
    ST_STUDENT_ROLL,        # 2
    ST_SCORING,             # 3
    ST_NOTE,                # 4  — interviewer short note before remark
    ST_REMARK,              # 5  — approve/edit auto remark
    ST_REMARK_EDIT,         # 6  — free-text edit of remark
    ST_SUMMARY,             # 7
    ST_EDIT_SECTION,        # 8
    ST_AFTER_SUBMIT,        # 9
    ST_DOWNLOAD_QUERY,      # 10
    ST_DOWNLOAD_SELECT,     # 11
    ST_MANAGER_PASSWORD,    # 12
    ST_MANAGER_MENU,        # 13
) = range(14)

# ── MarkdownV2 escaping ────────────────────────────────────────────
_MDV2_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')
def esc(t: str) -> str:
    return _MDV2_RE.sub(r'\\\1', str(t))

# ── Session helpers ────────────────────────────────────────────────
def gs(context):
    if "session" not in context.user_data:
        context.user_data["session"] = {}
    return context.user_data["session"]

def rs(context):
    context.user_data["session"]   = {}
    context.user_data["edit_mode"] = False

# ── Keyboards ──────────────────────────────────────────────────────
def iv_kbd():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💼 Ravi Sir",        callback_data="iv|ravi")],
        [InlineKeyboardButton("👩‍💼 Nikki Ma'am",     callback_data="iv|nikki")],
        [InlineKeyboardButton("👨‍💼 Amit Sir",        callback_data="iv|amit")],
        [InlineKeyboardButton("👩‍💼 Raksha Ma'am",    callback_data="iv|raksha")],
        [InlineKeyboardButton("👩‍💼 Shivangi Ma'am",  callback_data="iv|shivangi")],
    ])

def score_kbd(idx, edit_mode=False):
    btns = [InlineKeyboardButton(str(i), callback_data=f"score|{idx}|{i}") for i in range(6)]
    rows = [btns[:3], btns[3:]]
    nav  = []
    if edit_mode:
        nav.append(InlineKeyboardButton("↩️ Back to Summary", callback_data="edit_back_summary"))
    else:
        if idx > 0:
            nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"back|{idx}"))
    nav.append(InlineKeyboardButton("⏭️ Skip", callback_data=f"skip|{idx}"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

def edit_sec_kbd(scores):
    btns = []
    for i, sec in enumerate(SECTIONS):
        val = scores.get(i)
        btns.append([InlineKeyboardButton(
            f"{i+1}. {sec[:22]} ({'—' if val is None else val})",
            callback_data=f"edit_sec|{i}"
        )])
    btns.append([InlineKeyboardButton("✅ Done — Back to Summary", callback_data="edit_done")])
    return InlineKeyboardMarkup(btns)

# ── Summary text ───────────────────────────────────────────────────
def summary_text(session):
    lines = [
        f"📊 *Review Your Scores \\— {esc(session['interviewer_name'])}*",
        f"Student: {esc(session['student_name'])} \\| Roll: {esc(session['student_roll'])}",
        "",
    ]
    for i, sec in enumerate(SECTIONS):
        val = session["scores"].get(i)
        display = f"{val}/5" if val is not None else "\\—"
        lines.append(f"{i+1}\\. {esc(sec)} → *{esc(display)}*")
    return "\n".join(lines)

# ── Show section ───────────────────────────────────────────────────
async def _show_section(q_or_m, context, idx, edit_mode=False):
    session  = gs(context)
    session["current_sec"] = idx
    existing = session["scores"].get(idx)
    note     = f"\n_Current: {existing}/5_" if existing is not None else ""
    text = (
        f"📋 *Section {idx+1} of {len(SECTIONS)}*\n"
        f"*{esc(SECTIONS[idx])}*{note}\n\n"
        f"Select score \\(0\\–5\\):"
    )
    kbd = score_kbd(idx, edit_mode)
    if hasattr(q_or_m, "edit_message_text"):
        await q_or_m.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd)
    else:
        await q_or_m.reply_text(text, parse_mode="MarkdownV2", reply_markup=kbd)

# ── Show summary ───────────────────────────────────────────────────
async def _show_summary(query, context):
    session = gs(context)
    scored  = [v for v in session["scores"].values() if v is not None]
    if not scored:
        await query.edit_message_text(
            "⚠️ You haven't scored any section\\. Please score at least one section\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Start Scoring Again", callback_data="restart_scoring")
            ]]),
        )
        return False
    await query.edit_message_text(
        summary_text(session), parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Edit a Section",   callback_data="edit_section"),
            InlineKeyboardButton("✅ Confirm & Submit", callback_data="confirm_submit"),
        ]]),
    )
    return True

# ── Send report helper ─────────────────────────────────────────────
async def _send_report(bot, chat_id, student_name, student_roll, report_data, date_str):
    grand_avg = report_data["grand_avg"]
    n         = len(report_data["evaluators"])
    if grand_avg >= 40:
        verdict = (
            "✅ Your interview performance was good\\! Still, if you want to improve further, "
            "you can directly book another interview session through our bot\\."
        )
    else:
        verdict = (
            "⚠️ You should take 2\\–3 more mock interview sessions through our bot "
            "before your actual interview and work on your weak areas\\."
        )
    text = (
        f"🎓 *IB SA Mock Interview Result*\n"
        f"Student: *{esc(student_name)}*\n"
        f"Roll No: *{esc(student_roll)}*\n"
        f"Date: {esc(date_str)}\n"
        f"Total Score: *{esc(str(grand_avg))}/50* "
        f"\\(Avg of {n} evaluator{'s' if n>1 else ''}\\)\n\n"
        f"{verdict}\n\n"
        f"📎 Book your session: http://t\\.me/pg\\_appointment\\_bot"
    )
    await bot.send_message(chat_id=chat_id, text=text,
                           parse_mode="MarkdownV2", disable_web_page_preview=True)
    await asyncio.sleep(0.4)
    pdf_path = generate_pdf(student_name, student_roll, date_str, report_data)
    with open(pdf_path, "rb") as f:
        await bot.send_document(
            chat_id=chat_id, document=f,
            filename=f"Interview_Report_{student_roll}.pdf",
            caption="📄 IB SA Mock Interview Evaluation Report — Pareeksha Gurukul",
        )
    return pdf_path

# ══════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rs(context)
    await update.effective_message.reply_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n"
        "_IB SA Mock Interview Evaluation_\n\n"
        "Please select your name:",
        parse_mode="MarkdownV2",
        reply_markup=iv_kbd(),
    )
    return ST_SELECT_INTERVIEWER

# ── Select interviewer ─────────────────────────────────────────────
async def select_interviewer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    key   = query.data.split("|")[1]

    # Manager route
    if key == MANAGER_KEY:
        await query.edit_message_text(
            f"🔐 Hello, *{esc(MANAGER_NAME)}*\\!\n\nPlease enter your password:",
            parse_mode="MarkdownV2",
        )
        gs(context)["manager_pending"] = True
        return ST_MANAGER_PASSWORD

    iv_name = INTERVIEWERS[key]
    session = gs(context)
    session["interviewer_key"]  = key
    session["interviewer_name"] = iv_name

    recent = db.get_recent_students(minutes=STUDENT_CACHE_MINUTES)
    if recent:
        context.user_data["recent_students"] = recent
        btns = [[InlineKeyboardButton(
            f"👤 {s['name']}  |  {s['roll']}", callback_data=f"pick_student|{i}"
        )] for i, s in enumerate(recent)]
        btns.append([InlineKeyboardButton("➕ Enter New Student", callback_data="new_student")])
        await query.edit_message_text(
            f"👋 Hello, *{esc(iv_name)}*\\!\n\nSelect a recent student or add new:",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(btns),
        )
    else:
        await query.edit_message_text(
            f"👋 Hello, *{esc(iv_name)}*\\!\n\nPlease enter the *student's full name*:",
            parse_mode="MarkdownV2",
        )
    return ST_STUDENT_NAME

# ── Manager password ───────────────────────────────────────────────
async def manager_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entered = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    if entered != MANAGER_PASSWORD:
        await update.message.reply_text(
            "❌ Incorrect password\\. Send /start to try again\\.",
            parse_mode="MarkdownV2",
        )
        return ConversationHandler.END
    await update.message.reply_text(
        f"✅ *Welcome, {esc(MANAGER_NAME)}\\!*\n\nWhat would you like to do?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Last Report",    callback_data="mgr|last")],
            [InlineKeyboardButton("📅 Today's Reports", callback_data="mgr|today")],
            [InlineKeyboardButton("📦 All Reports ZIP", callback_data="mgr|all")],
        ]),
    )
    return ST_MANAGER_MENU

# ── Manager menu actions ───────────────────────────────────────────
async def manager_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query  = update.callback_query
    await query.answer()
    action = query.data.split("|")[1]
    bot    = context.bot
    chat_id = query.message.chat_id

    if action == "last":
        await query.edit_message_text("⏳ Fetching last report\\.\\.\\.", parse_mode="MarkdownV2")
        roll = db.get_last_report()
        if not roll:
            await bot.send_message(chat_id=chat_id,
                text="❌ No reports generated yet\\.", parse_mode="MarkdownV2")
        else:
            report_data = db.compile_report(roll)
            if report_data:
                pdf = generate_pdf(report_data["student_name"], roll,
                                   report_data["date"], report_data)
                with open(pdf, "rb") as f:
                    await bot.send_document(chat_id=chat_id, document=f,
                        filename=f"LastReport_{roll}.pdf",
                        caption=f"📄 Last report: {report_data['student_name']} | {roll}")

    elif action == "today":
        await query.edit_message_text("⏳ Fetching today's reports\\.\\.\\.", parse_mode="MarkdownV2")
        rolls = db.get_today_reports()
        if not rolls:
            await bot.send_message(chat_id=chat_id,
                text="📭 No reports generated today\\.", parse_mode="MarkdownV2")
        else:
            await bot.send_message(chat_id=chat_id,
                text=f"📅 *Today's Reports* \\— {esc(str(len(rolls)))} student\\(s\\)",
                parse_mode="MarkdownV2")
            for roll in rolls:
                report_data = db.compile_report(roll)
                if not report_data:
                    continue
                pdf = generate_pdf(report_data["student_name"], roll,
                                   report_data["date"], report_data)
                with open(pdf, "rb") as f:
                    await bot.send_document(chat_id=chat_id, document=f,
                        filename=f"Report_{roll}.pdf",
                        caption=f"📄 {report_data['student_name']} | {roll} | Avg: {report_data['grand_avg']}/50")
                await asyncio.sleep(0.5)

    elif action == "all":
        await query.edit_message_text("⏳ Building ZIP of all reports\\.\\.\\.", parse_mode="MarkdownV2")
        rolls = db.get_all_reports()
        if not rolls:
            await bot.send_message(chat_id=chat_id,
                text="📭 No reports generated yet\\.", parse_mode="MarkdownV2")
        else:
            zip_path = db.build_all_zip()
            with open(zip_path, "rb") as f:
                await bot.send_document(chat_id=chat_id, document=f,
                    filename="All_Interview_Reports.zip",
                    caption=f"📦 All reports — {len(rolls)} student(s)")

    # Show menu again
    await bot.send_message(
        chat_id=chat_id,
        text="What else would you like?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Last Report",    callback_data="mgr|last")],
            [InlineKeyboardButton("📅 Today's Reports", callback_data="mgr|today")],
            [InlineKeyboardButton("📦 All Reports ZIP", callback_data="mgr|all")],
            [InlineKeyboardButton("🔚 Exit",           callback_data="mgr|exit")],
        ]),
    )
    return ST_MANAGER_MENU

async def manager_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rs(context)
    await query.edit_message_text("👋 Manager session ended\\. Send /start to begin\\.",
                                   parse_mode="MarkdownV2")
    return ConversationHandler.END

# ── Pick recent student ────────────────────────────────────────────
async def pick_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query  = update.callback_query
    await query.answer()
    idx    = int(query.data.split("|")[1])
    recent = context.user_data.get("recent_students", [])
    if idx >= len(recent):
        await query.edit_message_text("❌ Not found\\. Please enter manually:", parse_mode="MarkdownV2")
        return ST_STUDENT_NAME
    s       = recent[idx]
    session = gs(context)
    session["student_name"] = s["name"]
    session["student_roll"] = s["roll"]
    session["scores"]       = {}
    session["current_sec"]  = 0
    await _show_section(query, context, 0)
    return ST_SCORING

async def new_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the *student's full name*:", parse_mode="MarkdownV2")
    return ST_STUDENT_NAME

async def student_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = gs(context)
    session["student_name"] = update.message.text.strip()
    await update.message.reply_text("Now enter the *student's Roll Number*:", parse_mode="MarkdownV2")
    return ST_STUDENT_ROLL

async def student_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = gs(context)
    session["student_roll"] = update.message.text.strip()
    session["scores"]       = {}
    session["current_sec"]  = 0
    await update.message.reply_text(
        f"📋 *Confirm Student Details*\n\n"
        f"Name: *{esc(session['student_name'])}*\n"
        f"Roll: *{esc(session['student_roll'])}*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Correct — Start Scoring", callback_data="confirm_student"),
            InlineKeyboardButton("✏️ Edit Details",            callback_data="edit_student"),
        ]]),
    )
    return ST_SCORING

async def confirm_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = gs(context)
    db.add_recent_student(session["student_name"], session["student_roll"])
    await _show_section(query, context, 0)
    return ST_SCORING

async def edit_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the *student's full name* again:", parse_mode="MarkdownV2")
    return ST_STUDENT_NAME

# ── Scoring callbacks ──────────────────────────────────────────────
async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str, score_str = query.data.split("|")
    idx   = int(idx_str)
    score = int(score_str)
    session = gs(context)
    session["scores"][idx] = score
    edit_mode = context.user_data.get("edit_mode", False)
    if edit_mode:
        context.user_data["edit_mode"] = False
        shown = await _show_summary(query, context)
        return ST_SUMMARY if shown else ST_SCORING
    if idx + 1 < len(SECTIONS):
        await _show_section(query, context, idx + 1)
        return ST_SCORING
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    gs(context)["scores"].pop(idx, None)
    edit_mode = context.user_data.get("edit_mode", False)
    if edit_mode:
        context.user_data["edit_mode"] = False
        shown = await _show_summary(query, context)
        return ST_SUMMARY if shown else ST_SCORING
    if idx + 1 < len(SECTIONS):
        await _show_section(query, context, idx + 1)
        return ST_SCORING
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    if idx == 0:
        await query.edit_message_text("Please re\\-enter the *student's Roll Number*:", parse_mode="MarkdownV2")
        return ST_STUDENT_ROLL
    await _show_section(query, context, idx - 1)
    return ST_SCORING

async def restart_scoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = gs(context)
    session["scores"] = {}
    context.user_data["edit_mode"] = False
    await _show_section(query, context, 0)
    return ST_SCORING

async def edit_back_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["edit_mode"] = False
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

async def edit_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = gs(context)
    await query.edit_message_text(
        "✏️ *Which section do you want to edit?*",
        parse_mode="MarkdownV2",
        reply_markup=edit_sec_kbd(session["scores"]),
    )
    return ST_EDIT_SECTION

async def edit_sec_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    context.user_data["edit_mode"] = True
    await _show_section(query, context, idx, edit_mode=True)
    return ST_SCORING

async def edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

# ── After summary confirmed → ask for short note ──────────────────
async def ask_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Interviewer types a short note — bot will build auto remark from it + scores."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 *Enter a short note about the candidate:*\n"
        "_\\(e\\.g\\. 'good communication, nervous, strong awareness'\\)_\n\n"
        "Bot will auto\\-generate the full remark from your note and scores\\.",
        parse_mode="MarkdownV2",
    )
    return ST_NOTE

async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive short note, build auto remark, show to interviewer for approval."""
    session  = gs(context)
    iv_note  = update.message.text.strip()
    session["iv_note"] = iv_note
    scores   = session["scores"]

    # Build auto remark
    auto_remark = db.build_remark(scores, iv_note)
    session["auto_remark"] = auto_remark

    await update.message.reply_text(
        f"📋 *Auto\\-Generated Remark:*\n\n"
        f"_{esc(auto_remark)}_\n\n"
        f"Submit this remark or edit it?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Submit This Remark", callback_data="remark_submit")],
            [InlineKeyboardButton("✏️ Edit Remark",        callback_data="remark_edit")],
        ]),
    )
    return ST_REMARK

async def remark_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Interviewer approved auto remark — save and proceed."""
    query = update.callback_query
    await query.answer()
    session = gs(context)
    session["final_remark"] = session.get("auto_remark", "")
    return await _save_and_ask_next(query, context)

async def remark_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Interviewer wants to edit — show text input."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ *Type your remark below:*\n_\\(Full text, as detailed as you like\\)_",
        parse_mode="MarkdownV2",
    )
    return ST_REMARK_EDIT

async def receive_edited_remark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive edited remark — save and proceed."""
    session = gs(context)
    remark  = update.message.text.strip()
    if not remark:
        await update.message.reply_text("⚠️ Please enter a valid remark\\.", parse_mode="MarkdownV2")
        return ST_REMARK_EDIT
    session["final_remark"] = remark
    # Fake a query-like object for _save_and_ask_next
    # We need to send a new message instead of editing
    iv_key   = session["interviewer_key"]
    iv_name  = session["interviewer_name"]
    s_name   = session["student_name"]
    s_roll   = session["student_roll"]
    scores   = session["scores"]
    remark   = session["final_remark"]
    date_str = datetime.now().strftime("%d %b %Y")

    db.save_report(s_roll, s_name, date_str, iv_key, iv_name, scores, remark)
    total = sum(v for v in scores.values() if v is not None)
    await update.message.reply_text(
        f"✅ *Report submitted\\!*\n"
        f"_{esc(iv_name)}_ → _{esc(s_name)}_ \\| Roll: _{esc(s_roll)}_\n"
        f"Your total: *{total}/50*\n\nWhat next?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ More Interviewers Will Submit", callback_data="more_ivs")],
            [InlineKeyboardButton("📊 Generate Final Report Now",    callback_data="gen_report")],
        ]),
    )
    return ST_AFTER_SUBMIT

async def _save_and_ask_next(query, context):
    """Save report from callback query path and show after-submit options."""
    session  = gs(context)
    iv_key   = session["interviewer_key"]
    iv_name  = session["interviewer_name"]
    s_name   = session["student_name"]
    s_roll   = session["student_roll"]
    scores   = session["scores"]
    remark   = session.get("final_remark", session.get("auto_remark", ""))
    date_str = datetime.now().strftime("%d %b %Y")

    db.save_report(s_roll, s_name, date_str, iv_key, iv_name, scores, remark)
    total = sum(v for v in scores.values() if v is not None)
    await query.edit_message_text(
        f"✅ *Report submitted\\!*\n"
        f"_{esc(iv_name)}_ → _{esc(s_name)}_ \\| Roll: _{esc(s_roll)}_\n"
        f"Your total: *{total}/50*\n\nWhat next?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ More Interviewers Will Submit", callback_data="more_ivs")],
            [InlineKeyboardButton("📊 Generate Final Report Now",    callback_data="gen_report")],
        ]),
    )
    return ST_AFTER_SUBMIT

# ── After submit ───────────────────────────────────────────────────
async def more_interviewers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = gs(context)
    await query.edit_message_text(
        f"⏳ *Waiting for more evaluators*\n\n"
        f"Next interviewer should open the bot and submit for:\n\n"
        f"👤 *{esc(session['student_name'])}* \\| Roll: *{esc(session['student_roll'])}*\n\n"
        f"Come back here and tap Generate Report when done\\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📊 Generate Final Report Now", callback_data="gen_report"),
        ]]),
    )
    return ST_AFTER_SUBMIT

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = gs(context)
    s_name  = session["student_name"]
    s_roll  = session["student_roll"]

    reports = db.get_reports(s_roll)
    if len(reports) < 2:
        await query.edit_message_text(
            "⚠️ *Minimum 2 evaluators required\\.*\n"
            "Please have another interviewer submit first\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Check Again", callback_data="gen_report"),
            ]]),
        )
        return ST_AFTER_SUBMIT

    await query.edit_message_text("⏳ Generating report\\.\\.\\.", parse_mode="MarkdownV2")

    report_data = db.compile_report(s_roll)
    date_str    = report_data["date"]
    bot         = context.bot

    await _send_report(bot, query.message.chat_id, s_name, s_roll, report_data, date_str)

    # Mark as generated for manager download
    db.mark_generated(s_roll)

    # Send to group
    group_ok = True
    try:
        await _send_report(bot, GROUP_ID, s_name, s_roll, report_data, date_str)
        logger.info(f"Group report sent OK for {s_roll}")
    except Exception as e:
        group_ok = False
        err_msg  = f"{type(e).__name__}: {str(e)[:120]}"
        logger.error(f"Group send FAILED for {s_roll}: {err_msg}")
        try:
            await bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "⚠️ *Group delivery failed\\!*\n"
                    f"Error: `{esc(err_msg)}`\n\n"
                    "Please ensure bot is added to the group and has send permissions\\."
                ),
                parse_mode="MarkdownV2",
            )
        except Exception:
            pass

    db.remove_recent_student(s_roll)

    result_text = (
        "✅ *Report sent successfully\\!*"
        if group_ok else
        "✅ *Report sent to you\\!* ⚠️ Group delivery failed \\— check bot permissions\\."
    )
    await bot.send_message(
        chat_id=query.message.chat_id,
        text=result_text,
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Start New Evaluation", callback_data="new_eval"),
        ]]),
    )
    return ST_AFTER_SUBMIT

async def new_eval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rs(context)
    await query.edit_message_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n"
        "_IB SA Mock Interview Evaluation_\n\n"
        "Please select your name:",
        parse_mode="MarkdownV2",
        reply_markup=iv_kbd(),
    )
    return ST_SELECT_INTERVIEWER

# ══════════════════════════════════════════════════════════════════
# /download — search by name or roll
# ══════════════════════════════════════════════════════════════════
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔍 *Search Report*\n\nEnter student name or roll number:",
        parse_mode="MarkdownV2",
    )
    return ST_DOWNLOAD_QUERY

async def download_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q_text  = update.message.text.strip()
    results = db.search_student(q_text)
    if not results:
        await update.message.reply_text(
            f"❌ No report found for *{esc(q_text)}*\\. Try again or /cancel\\.",
            parse_mode="MarkdownV2",
        )
        return ST_DOWNLOAD_QUERY
    if len(results) == 1:
        await _send_download(context.bot, update.effective_chat.id, results[0]["roll"])
        return ConversationHandler.END
    context.user_data["dl_results"] = results
    btns = [[InlineKeyboardButton(
        f"{r['name']} — {r['roll']}", callback_data=f"dl|{i}"
    )] for i, r in enumerate(results)]
    await update.message.reply_text(
        "📁 *Multiple records found\\. Select one:*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(btns),
    )
    return ST_DOWNLOAD_SELECT

async def download_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx     = int(query.data.split("|")[1])
    results = context.user_data.get("dl_results", [])
    if idx >= len(results):
        await query.edit_message_text("❌ Error\\. Please try /download again\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END
    await query.edit_message_text("⏳ Fetching report\\.\\.\\.", parse_mode="MarkdownV2")
    await _send_download(context.bot, query.message.chat_id, results[idx]["roll"])
    return ConversationHandler.END

async def _send_download(bot, chat_id, roll):
    report_data = db.compile_report(roll)
    if not report_data:
        await bot.send_message(chat_id=chat_id,
                               text="❌ Report not found or incomplete\\.", parse_mode="MarkdownV2")
        return
    pdf = generate_pdf(report_data["student_name"], roll, report_data["date"], report_data)
    with open(pdf, "rb") as f:
        await bot.send_document(
            chat_id=chat_id, document=f,
            filename=f"Interview_Report_{roll}.pdf",
            caption=f"📄 Report: {report_data['student_name']} | {roll}",
        )

# ══════════════════════════════════════════════════════════════════
# /help
# ══════════════════════════════════════════════════════════════════
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Pareeksha Gurukul Interview Bot*\n\n"
        "*Commands:*\n"
        "/start \\— Begin a new evaluation\n"
        "/download \\— Search and download a student report by name or roll number\n"
        "/help \\— Show this help message\n"
        "/cancel \\— Cancel current session\n\n"
        "*How it works:*\n"
        "1\\. Select your name\n"
        "2\\. Select or enter student details\n"
        "3\\. Score 10 sections \\(0\\-5 each\\)\n"
        "4\\. Enter a short note — bot auto\\-generates remark\n"
        "5\\. Approve or edit the remark\n"
        "6\\. Minimum 2 evaluators needed to generate final report\n"
        "7\\. Final PDF sent to you and admin group\n\n"
        "*Manager Panel:*\n"
        "Select Shivangi Ma'am → enter password to access\\.",
        parse_mode="MarkdownV2",
    )

# ── /cancel ────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rs(context)
    await update.message.reply_text(
        "❌ Cancelled\\. Send /start to begin again\\.", parse_mode="MarkdownV2"
    )
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    main_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ST_SELECT_INTERVIEWER: [
                CallbackQueryHandler(select_interviewer, pattern=r"^iv\|"),
            ],
            ST_MANAGER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manager_password),
            ],
            ST_MANAGER_MENU: [
                CallbackQueryHandler(manager_menu, pattern=r"^mgr\|(?!exit)"),
                CallbackQueryHandler(manager_exit, pattern=r"^mgr\|exit$"),
            ],
            ST_STUDENT_NAME: [
                CallbackQueryHandler(pick_student,  pattern=r"^pick_student\|"),
                CallbackQueryHandler(new_student,   pattern=r"^new_student$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_name),
            ],
            ST_STUDENT_ROLL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_roll),
            ],
            ST_SCORING: [
                CallbackQueryHandler(confirm_student,   pattern=r"^confirm_student$"),
                CallbackQueryHandler(edit_student,      pattern=r"^edit_student$"),
                CallbackQueryHandler(handle_score,      pattern=r"^score\|"),
                CallbackQueryHandler(handle_skip,       pattern=r"^skip\|"),
                CallbackQueryHandler(handle_back,       pattern=r"^back\|"),
                CallbackQueryHandler(restart_scoring,   pattern=r"^restart_scoring$"),
                CallbackQueryHandler(edit_back_summary, pattern=r"^edit_back_summary$"),
            ],
            ST_SUMMARY: [
                CallbackQueryHandler(edit_section, pattern=r"^edit_section$"),
                CallbackQueryHandler(ask_note,     pattern=r"^confirm_submit$"),
            ],
            ST_EDIT_SECTION: [
                CallbackQueryHandler(edit_sec_select, pattern=r"^edit_sec\|"),
                CallbackQueryHandler(edit_done,       pattern=r"^edit_done$"),
            ],
            ST_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note),
            ],
            ST_REMARK: [
                CallbackQueryHandler(remark_submit, pattern=r"^remark_submit$"),
                CallbackQueryHandler(remark_edit,   pattern=r"^remark_edit$"),
            ],
            ST_REMARK_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edited_remark),
            ],
            ST_AFTER_SUBMIT: [
                CallbackQueryHandler(more_interviewers, pattern=r"^more_ivs$"),
                CallbackQueryHandler(generate_report,   pattern=r"^gen_report$"),
                CallbackQueryHandler(new_eval,          pattern=r"^new_eval$"),
                CallbackQueryHandler(select_interviewer,pattern=r"^iv\|"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False,
        allow_reentry=True,
    )

    dl_conv = ConversationHandler(
        entry_points=[CommandHandler("download", download_cmd)],
        states={
            ST_DOWNLOAD_QUERY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, download_query)],
            ST_DOWNLOAD_SELECT: [CallbackQueryHandler(download_select, pattern=r"^dl\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False,
        allow_reentry=True,
    )

    app.add_handler(main_conv)
    app.add_handler(dl_conv)
    app.add_handler(CommandHandler("help", help_cmd))

    logger.info("Bot started — polling")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
