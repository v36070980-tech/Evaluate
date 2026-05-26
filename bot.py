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
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID  = int(os.environ["GROUP_ID"])

INTERVIEWERS = {
    "ravi":   "Ravi Sir",
    "nikki":  "Nikki Ma'am",
    "amit":   "Amit Sir",
    "raksha": "Raksha Ma'am",
}

SECTIONS = [
    "Body Language",
    "Communication",
    "Skills & Functions",
    "Situational Handling Aptitude",
    "Stress Handling",
    "Team Work",
    "Presence of Mind",
    "Awareness",
    "Clarity of Thoughts",
    "Integrity",
]

STUDENT_CACHE_MINUTES = 20

# ── States ─────────────────────────────────────────────────────────
(
    ST_SELECT_INTERVIEWER,  # 0
    ST_STUDENT_NAME,        # 1
    ST_STUDENT_ROLL,        # 2
    ST_SCORING,             # 3  — scoring sections forward
    ST_EDIT_ONE,            # 4  — scoring ONE section then back to summary (FIX for edit flow)
    ST_REMARK,              # 5
    ST_SUMMARY,             # 6
    ST_EDIT_SECTION,        # 7  — choosing which section to edit
    ST_AFTER_SUBMIT,        # 8
    ST_DOWNLOAD_QUERY,      # 9
    ST_DOWNLOAD_SELECT,     # 10
) = range(11)

# ── MarkdownV2 safe escaping ───────────────────────────────────────
_MDV2_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')
def esc(text: str) -> str:
    return _MDV2_RE.sub(r'\\\1', str(text))

# ── Session helpers ────────────────────────────────────────────────
def get_session(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "session" not in context.user_data:
        context.user_data["session"] = {}
    return context.user_data["session"]

def reset_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["session"] = {}

# ── Keyboards ──────────────────────────────────────────────────────
def interviewer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💼 Ravi Sir",     callback_data="iv|ravi")],
        [InlineKeyboardButton("👩‍💼 Nikki Ma'am",  callback_data="iv|nikki")],
        [InlineKeyboardButton("👨‍💼 Amit Sir",     callback_data="iv|amit")],
        [InlineKeyboardButton("👩‍💼 Raksha Ma'am", callback_data="iv|raksha")],
    ])

def scores_keyboard(section_idx: int, edit_mode: bool = False) -> InlineKeyboardMarkup:
    """
    Scoring keyboard for one section.
    edit_mode=True  → Back goes to summary (not previous section)
    edit_mode=False → Back goes to previous section (or roll entry if idx=0)
    """
    score_btns = [
        InlineKeyboardButton(str(i), callback_data=f"score|{section_idx}|{i}")
        for i in range(6)
    ]
    rows = [score_btns[:3], score_btns[3:]]
    nav  = []
    if edit_mode:
        nav.append(InlineKeyboardButton("↩️ Back to Summary", callback_data="edit_back_summary"))
    else:
        if section_idx > 0:
            nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"back|{section_idx}"))
    nav.append(InlineKeyboardButton("⏭️ Skip", callback_data=f"skip|{section_idx}"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

def edit_sections_keyboard(scores: dict) -> InlineKeyboardMarkup:
    btns = []
    for i, sec in enumerate(SECTIONS):
        val   = scores.get(i)
        label = f"{i+1}. {sec[:22]} ({'—' if val is None else val})"
        btns.append([InlineKeyboardButton(label, callback_data=f"edit_sec|{i}")])
    btns.append([InlineKeyboardButton("✅ Done — Back to Summary", callback_data="edit_done")])
    return InlineKeyboardMarkup(btns)

# ── Summary text ───────────────────────────────────────────────────
def summary_text(session: dict) -> str:
    iv_name = session["interviewer_name"]
    name    = session["student_name"]
    roll    = session["student_roll"]
    scores  = session["scores"]
    lines   = [
        f"📊 *Review Your Scores — {esc(iv_name)}*",
        f"Student: {esc(name)} \\| Roll: {esc(roll)}",
        "",
    ]
    for i, sec in enumerate(SECTIONS):
        val     = scores.get(i)
        display = f"{val}/5" if val is not None else "—"
        lines.append(f"{i+1}\\. {esc(sec)} → *{esc(display)}*")
    return "\n".join(lines)

# ── Summary display (pure helper — callers set state) ─────────────
async def _show_summary(query, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Render the summary screen.
    Returns True  → scores exist, summary shown   → caller returns ST_SUMMARY
    Returns False → no scores at all              → caller returns ST_SCORING
    """
    session = get_session(context)
    scored  = [v for v in session["scores"].values() if v is not None]
    if not scored:
        await query.edit_message_text(
            "⚠️ You haven't scored any section\\.\n"
            "Please score at least one section to submit\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Start Scoring Again", callback_data="restart_scoring"),
            ]]),
        )
        return False
    text = summary_text(session)
    kbd  = InlineKeyboardMarkup([[
        InlineKeyboardButton("✏️ Edit a Section",   callback_data="edit_section"),
        InlineKeyboardButton("✅ Confirm & Submit", callback_data="confirm_submit"),
    ]])
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd)
    return True

# ── Section display ────────────────────────────────────────────────
async def _show_section(
    query_or_msg, context: ContextTypes.DEFAULT_TYPE,
    idx: int, edit_mode: bool = False
) -> None:
    session  = get_session(context)
    session["current_sec"] = idx
    sec_name = SECTIONS[idx]
    existing = session["scores"].get(idx)
    note     = f"\n_Current score: {existing}/5_" if existing is not None else ""
    text = (
        f"📋 *Section {idx+1} of {len(SECTIONS)}*\n"
        f"*{esc(sec_name)}*{note}\n\n"
        f"Select score \\(0–5\\):"
    )
    kbd = scores_keyboard(idx, edit_mode=edit_mode)
    if hasattr(query_or_msg, "edit_message_text"):
        await query_or_msg.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd)
    else:
        await query_or_msg.reply_text(text, parse_mode="MarkdownV2", reply_markup=kbd)

# ── Send report (text + PDF) ───────────────────────────────────────
async def send_report(
    bot, chat_id: int,
    student_name: str, student_roll: str,
    report_data: dict, date_str: str
) -> str:
    grand_avg  = report_data["grand_avg"]
    n          = len(report_data["evaluators"])

    if grand_avg >= 40:
        verdict = (
            "✅ Your interview performance was good\\! Still, if you want to improve further, "
            "you can directly book another interview session through our bot\\."
        )
    else:
        verdict = (
            "⚠️ You should take 2–3 more mock interview sessions through our bot before "
            "your actual interview and work on your weak areas\\."
        )

    text = (
        f"🎓 *IB SA Mock Interview Result*\n"
        f"Student: *{esc(student_name)}*\n"
        f"Roll No: *{esc(student_roll)}*\n"
        f"Date: {esc(date_str)}\n"
        f"Total Score: *{esc(str(grand_avg))}/50* "
        f"\\(Avg of {n} evaluator{'s' if n > 1 else ''}\\)\n\n"
        f"{verdict}\n\n"
        f"📎 Book your session: http://t\\.me/pg\\_appointment\\_bot"
    )
    await bot.send_message(
        chat_id=chat_id, text=text,
        parse_mode="MarkdownV2", disable_web_page_preview=True
    )
    await asyncio.sleep(0.5)
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
    reset_session(context)
    await update.effective_message.reply_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n"
        "_IB SA Mock Interview Evaluation_\n\n"
        "Please select your name:",
        parse_mode="MarkdownV2",
        reply_markup=interviewer_keyboard(),
    )
    return ST_SELECT_INTERVIEWER

# ── Select interviewer ─────────────────────────────────────────────
async def select_interviewer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    key     = query.data.split("|")[1]
    iv_name = INTERVIEWERS[key]
    session = get_session(context)
    session["interviewer_key"]  = key
    session["interviewer_name"] = iv_name

    recent = db.get_recent_students(minutes=STUDENT_CACHE_MINUTES)
    if recent:
        context.user_data["recent_students"] = recent
        btns = []
        for idx, s in enumerate(recent):
            label = f"👤 {s['name']}  |  {s['roll']}"
            btns.append([InlineKeyboardButton(label, callback_data=f"pick_student|{idx}")])
        btns.append([InlineKeyboardButton("➕ Enter New Student", callback_data="new_student")])
        await query.edit_message_text(
            f"👋 Hello, *{esc(iv_name)}*\\!\n\n"
            f"Select a recently entered student or add a new one:",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(btns),
        )
    else:
        await query.edit_message_text(
            f"👋 Hello, *{esc(iv_name)}*\\!\n\nPlease enter the *student's full name*:",
            parse_mode="MarkdownV2",
        )
    return ST_STUDENT_NAME

# ── Pick student from recent cache ─────────────────────────────────
async def pick_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query  = update.callback_query
    await query.answer()
    idx    = int(query.data.split("|")[1])
    recent = context.user_data.get("recent_students", [])
    if idx >= len(recent):
        await query.edit_message_text(
            "❌ Student not found\\. Please enter manually:",
            parse_mode="MarkdownV2",
        )
        return ST_STUDENT_NAME
    s       = recent[idx]
    session = get_session(context)
    session["student_name"] = s["name"]
    session["student_roll"] = s["roll"]
    session["scores"]       = {}
    session["current_sec"]  = 0
    await _show_section(query, context, 0)
    return ST_SCORING

async def new_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter the *student's full name*:", parse_mode="MarkdownV2"
    )
    return ST_STUDENT_NAME

# ── Student name ───────────────────────────────────────────────────
async def student_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name    = update.message.text.strip()
    session = get_session(context)
    session["student_name"] = name
    await update.message.reply_text(
        "Now enter the *student's Roll Number*:", parse_mode="MarkdownV2"
    )
    return ST_STUDENT_ROLL

# ── Student roll ───────────────────────────────────────────────────
async def student_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(context)
    session["student_roll"] = update.message.text.strip()
    session["scores"]       = {}
    session["current_sec"]  = 0
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Correct — Start Scoring", callback_data="confirm_student"),
        InlineKeyboardButton("✏️ Edit Details",            callback_data="edit_student"),
    ]])
    await update.message.reply_text(
        f"📋 *Confirm Student Details*\n\n"
        f"Name: *{esc(session['student_name'])}*\n"
        f"Roll: *{esc(session['student_roll'])}*",
        parse_mode="MarkdownV2",
        reply_markup=kbd,
    )
    return ST_SCORING

async def confirm_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = get_session(context)
    db.add_recent_student(session["student_name"], session["student_roll"])
    await _show_section(query, context, 0)
    return ST_SCORING

async def edit_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter the *student's full name* again:", parse_mode="MarkdownV2"
    )
    return ST_STUDENT_NAME

# ── Scoring: forward flow ──────────────────────────────────────────
async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str, score_str = query.data.split("|")
    idx   = int(idx_str)
    score = int(score_str)
    session = get_session(context)
    session["scores"][idx] = score

    # Check which mode we're in
    edit_mode = context.user_data.get("edit_mode", False)

    if edit_mode:
        # FIX: in edit mode, after scoring just one section → back to summary
        context.user_data["edit_mode"] = False
        shown = await _show_summary(query, context)
        return ST_SUMMARY if shown else ST_SCORING
    else:
        if idx + 1 < len(SECTIONS):
            await _show_section(query, context, idx + 1)
            return ST_SCORING
        else:
            shown = await _show_summary(query, context)
            return ST_SUMMARY if shown else ST_SCORING

async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    session = get_session(context)
    session["scores"].pop(idx, None)

    edit_mode = context.user_data.get("edit_mode", False)

    if edit_mode:
        # FIX: in edit mode, skipping also returns to summary
        context.user_data["edit_mode"] = False
        shown = await _show_summary(query, context)
        return ST_SUMMARY if shown else ST_SCORING
    else:
        if idx + 1 < len(SECTIONS):
            await _show_section(query, context, idx + 1)
            return ST_SCORING
        else:
            shown = await _show_summary(query, context)
            return ST_SUMMARY if shown else ST_SCORING

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    if idx == 0:
        await query.edit_message_text(
            "Please re\\-enter the *student's Roll Number*:", parse_mode="MarkdownV2"
        )
        return ST_STUDENT_ROLL
    await _show_section(query, context, idx - 1)
    return ST_SCORING

async def restart_scoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    session = get_session(context)
    session["scores"] = {}
    context.user_data["edit_mode"] = False
    await _show_section(query, context, 0)
    return ST_SCORING

# ── Edit back to summary (from edit_mode) ──────────────────────────
async def edit_back_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User pressed 'Back to Summary' while in edit mode."""
    query = update.callback_query
    await query.answer()
    context.user_data["edit_mode"] = False
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

# ── Edit section chooser ───────────────────────────────────────────
async def edit_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = get_session(context)
    await query.edit_message_text(
        "✏️ *Which section do you want to edit?*",
        parse_mode="MarkdownV2",
        reply_markup=edit_sections_keyboard(session["scores"]),
    )
    return ST_EDIT_SECTION

async def edit_sec_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    FIX: Set edit_mode=True so that after scoring/skipping this section,
    the bot returns directly to summary instead of continuing forward.
    """
    query = update.callback_query
    await query.answer()
    idx   = int(query.data.split("|")[1])
    context.user_data["edit_mode"] = True
    await _show_section(query, context, idx, edit_mode=True)
    return ST_SCORING   # handle_score/skip will check edit_mode flag

async def edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    shown = await _show_summary(query, context)
    return ST_SUMMARY if shown else ST_SCORING

# ── Remark ─────────────────────────────────────────────────────────
async def ask_remark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 *Enter your Remark* for this student:\n_\\(Descriptive text only — no scores\\)_",
        parse_mode="MarkdownV2",
    )
    return ST_REMARK

async def receive_remark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    remark = update.message.text.strip()
    if not remark or remark.isdigit():
        await update.message.reply_text(
            "⚠️ Please enter a descriptive text remark, not just a number\\.",
            parse_mode="MarkdownV2",
        )
        return ST_REMARK

    session  = get_session(context)
    session["remark"] = remark
    iv_key   = session["interviewer_key"]
    iv_name  = session["interviewer_name"]
    s_name   = session["student_name"]
    s_roll   = session["student_roll"]
    scores   = session["scores"]
    date_str = datetime.now().strftime("%d %b %Y")

    db.save_report(s_roll, s_name, date_str, iv_key, iv_name, scores, remark)

    total_scored = sum(v for v in scores.values() if v is not None)
    kbd = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ More Interviewers Will Submit", callback_data="more_ivs")],
        [InlineKeyboardButton("📊 Generate Final Report Now",    callback_data="gen_report")],
    ])
    await update.message.reply_text(
        f"✅ *Report submitted\\!*\n"
        f"_{esc(iv_name)}_ → _{esc(s_name)}_ \\| Roll: _{esc(s_roll)}_\n"
        f"Your total: *{total_scored}/50*\n\n"
        f"What next?",
        parse_mode="MarkdownV2",
        reply_markup=kbd,
    )
    return ST_AFTER_SUBMIT

# ── After submit ───────────────────────────────────────────────────
async def more_interviewers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = get_session(context)
    s_name  = session["student_name"]
    s_roll  = session["student_roll"]
    await query.edit_message_text(
        f"⏳ *Waiting for more evaluators*\n\n"
        f"The next interviewer should open the bot on their own Telegram "
        f"and submit a report for:\n\n"
        f"👤 *{esc(s_name)}* \\| Roll: *{esc(s_roll)}*\n\n"
        f"Once all done, come back here and tap Generate Report\\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📊 Generate Final Report Now", callback_data="gen_report"),
        ]]),
    )
    return ST_AFTER_SUBMIT

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query   = update.callback_query
    await query.answer()
    session = get_session(context)
    s_name  = session["student_name"]
    s_roll  = session["student_roll"]

    reports = db.get_reports(s_roll)
    if len(reports) < 2:
        await query.edit_message_text(
            "⚠️ *Minimum 2 evaluators required\\.*\n"
            "Please have another interviewer submit their report first\\.",
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

    await send_report(bot, query.message.chat_id, s_name, s_roll, report_data, date_str)

    try:
        await send_report(bot, GROUP_ID, s_name, s_roll, report_data, date_str)
    except Exception as e:
        logger.error(f"Group send failed: {e}")

    db.remove_recent_student(s_roll)

    await bot.send_message(
        chat_id=query.message.chat_id,
        text="✅ *Report sent successfully\\!*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Start New Evaluation", callback_data="new_eval"),
        ]]),
    )
    return ST_AFTER_SUBMIT

async def new_eval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    reset_session(context)
    context.user_data["edit_mode"] = False
    await query.edit_message_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n"
        "_IB SA Mock Interview Evaluation_\n\n"
        "Please select your name:",
        parse_mode="MarkdownV2",
        reply_markup=interviewer_keyboard(),
    )
    return ST_SELECT_INTERVIEWER

# ══════════════════════════════════════════════════════════════════
# /download
# ══════════════════════════════════════════════════════════════════
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔍 *Search Report*\n\nEnter student name or roll number:",
        parse_mode="MarkdownV2",
    )
    return ST_DOWNLOAD_QUERY

async def download_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query_text = update.message.text.strip()
    results    = db.search_student(query_text)

    if not results:
        await update.message.reply_text(
            f"❌ No report found for *{esc(query_text)}*\\.\n"
            "Please check the name or roll number and try again\\.",
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
        await query.edit_message_text("❌ Selection error\\. Please try /download again\\.",
                                      parse_mode="MarkdownV2")
        return ConversationHandler.END
    await query.edit_message_text("⏳ Fetching your report\\.\\.\\.", parse_mode="MarkdownV2")
    await _send_download(context.bot, query.message.chat_id, results[idx]["roll"])
    return ConversationHandler.END

async def _send_download(bot, chat_id: int, roll: str) -> None:
    report_data = db.compile_report(roll)
    if not report_data:
        await bot.send_message(chat_id=chat_id,
                               text="❌ Report not found or incomplete\\.",
                               parse_mode="MarkdownV2")
        return
    pdf_path = generate_pdf(
        report_data["student_name"], roll, report_data["date"], report_data
    )
    with open(pdf_path, "rb") as f:
        await bot.send_document(
            chat_id=chat_id, document=f,
            filename=f"Interview_Report_{roll}.pdf",
            caption=f"📄 Report for {report_data['student_name']} | Roll: {roll}",
        )

# ── /cancel ────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reset_session(context)
    context.user_data["edit_mode"] = False
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
            ST_STUDENT_NAME: [
                CallbackQueryHandler(pick_student,  pattern=r"^pick_student\|"),
                CallbackQueryHandler(new_student,   pattern=r"^new_student$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_name),
            ],
            ST_STUDENT_ROLL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_roll),
            ],
            ST_SCORING: [
                CallbackQueryHandler(confirm_student,    pattern=r"^confirm_student$"),
                CallbackQueryHandler(edit_student,       pattern=r"^edit_student$"),
                CallbackQueryHandler(handle_score,       pattern=r"^score\|"),
                CallbackQueryHandler(handle_skip,        pattern=r"^skip\|"),
                CallbackQueryHandler(handle_back,        pattern=r"^back\|"),
                CallbackQueryHandler(restart_scoring,    pattern=r"^restart_scoring$"),
                CallbackQueryHandler(edit_back_summary,  pattern=r"^edit_back_summary$"),
            ],
            ST_SUMMARY: [
                CallbackQueryHandler(edit_section,       pattern=r"^edit_section$"),
                CallbackQueryHandler(ask_remark,         pattern=r"^confirm_submit$"),
            ],
            ST_EDIT_SECTION: [
                CallbackQueryHandler(edit_sec_select,    pattern=r"^edit_sec\|"),
                CallbackQueryHandler(edit_done,          pattern=r"^edit_done$"),
            ],
            ST_REMARK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remark),
            ],
            ST_AFTER_SUBMIT: [
                CallbackQueryHandler(more_interviewers,  pattern=r"^more_ivs$"),
                CallbackQueryHandler(generate_report,    pattern=r"^gen_report$"),
                CallbackQueryHandler(new_eval,           pattern=r"^new_eval$"),
                CallbackQueryHandler(select_interviewer, pattern=r"^iv\|"),
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
            ST_DOWNLOAD_QUERY:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, download_query),
            ],
            ST_DOWNLOAD_SELECT: [
                CallbackQueryHandler(download_select, pattern=r"^dl\|"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False,
        allow_reentry=True,
    )

    app.add_handler(main_conv)
    app.add_handler(dl_conv)

    logger.info("Bot started — polling")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
