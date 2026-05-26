import os
import json
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]
GROUP_ID    = int(os.environ["GROUP_ID"])   # admin group chat_id (negative number)

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

# ── States ────────────────────────────────────────────────────────
(
    ST_SELECT_INTERVIEWER,
    ST_STUDENT_NAME,
    ST_STUDENT_ROLL,
    ST_SCORING,
    ST_REMARK,
    ST_SUMMARY,
    ST_EDIT_SECTION,
    ST_AFTER_SUBMIT,
    ST_DOWNLOAD_QUERY,
    ST_DOWNLOAD_SELECT,
) = range(10)

# ── Helpers ───────────────────────────────────────────────────────
def get_session(context):
    if "session" not in context.user_data:
        context.user_data["session"] = {}
    return context.user_data["session"]

def reset_session(context):
    context.user_data["session"] = {}

def scores_keyboard(section_idx):
    score_btns = [InlineKeyboardButton(str(i), callback_data=f"score|{section_idx}|{i}") for i in range(6)]
    rows = [score_btns[:3], score_btns[3:]]
    nav = []
    if section_idx > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"back|{section_idx}"))
    nav.append(InlineKeyboardButton("⏭️ Skip", callback_data=f"skip|{section_idx}"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

def summary_text(session):
    iv_name = session["interviewer_name"]
    name    = session["student_name"]
    roll    = session["student_roll"]
    scores  = session["scores"]
    lines   = [f"📊 *Review Your Scores — {iv_name}*",
               f"Student: {name} | Roll: {roll}", ""]
    for i, sec in enumerate(SECTIONS):
        val = scores.get(i)
        display = f"{val}/5" if val is not None else "—"
        lines.append(f"{i+1}\\. {sec.replace('-','\\-').replace('.','\\.')} → *{display}*")
    return "\n".join(lines)

def edit_sections_keyboard(scores):
    btns = []
    for i, sec in enumerate(SECTIONS):
        val = scores.get(i)
        label = f"{i+1}. {sec[:20]} ({'—' if val is None else val})"
        btns.append([InlineKeyboardButton(label, callback_data=f"edit_sec|{i}")])
    btns.append([InlineKeyboardButton("✅ Done — Back to Summary", callback_data="edit_done")])
    return InlineKeyboardMarkup(btns)

async def send_report(bot, chat_id, student_name, student_roll, report_data, date_str):
    """Send text summary + PDF to a chat."""
    grand_avg = report_data["grand_avg"]
    evaluators = report_data["evaluators"]
    n = len(evaluators)

    if grand_avg >= 40:
        verdict = ("✅ Your interview performance was good\\! Still, if you want to improve "
                   "further, you can directly book another interview session through our bot\\.")
    else:
        verdict = ("⚠️ You should take 2–3 more mock interview sessions through our bot before "
                   "your actual interview and work on your weak areas\\.")

    text = (
        f"🎓 *IB SA Mock Interview Result*\n"
        f"Student: *{student_name}*\n"
        f"Roll No: *{student_roll}*\n"
        f"Date: {date_str}\n"
        f"Total Score: *{grand_avg}/50* \\(Avg of {n} evaluator{'s' if n>1 else ''}\\)\n\n"
        f"{verdict}\n\n"
        f"📎 Book your session: http://t\\.me/pg\\_appointment\\_bot"
    )
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2",
                           disable_web_page_preview=True)
    await asyncio.sleep(0.5)

    pdf_path = generate_pdf(student_name, student_roll, date_str, report_data)
    with open(pdf_path, "rb") as f:
        await bot.send_document(chat_id=chat_id, document=f,
                                filename=f"Interview_Report_{student_roll}.pdf",
                                caption="📄 IB SA Mock Interview Evaluation Report — Pareeksha Gurukul")
    return pdf_path

# ══════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    kbd = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💼 Ravi Sir",    callback_data="iv|ravi")],
        [InlineKeyboardButton("👩‍💼 Nikki Ma'am", callback_data="iv|nikki")],
        [InlineKeyboardButton("👨‍💼 Amit Sir",    callback_data="iv|amit")],
        [InlineKeyboardButton("👩‍💼 Raksha Ma'am",callback_data="iv|raksha")],
    ])
    await update.effective_message.reply_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n_IB SA Mock Interview Evaluation_\n\nPlease select your name:",
        parse_mode="MarkdownV2", reply_markup=kbd
    )
    return ST_SELECT_INTERVIEWER

# ── Select interviewer ────────────────────────────────────────────
async def select_interviewer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split("|")[1]
    session = get_session(context)
    session["interviewer_key"]  = key
    session["interviewer_name"] = INTERVIEWERS[key]
    await query.edit_message_text(
        f"👋 Hello, *{INTERVIEWERS[key]}*\\!\n\nPlease enter the *student's full name*:",
        parse_mode="MarkdownV2"
    )
    return ST_STUDENT_NAME

# ── Student name ──────────────────────────────────────────────────
async def student_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(context)
    session["student_name"] = update.message.text.strip()
    await update.message.reply_text("Now enter the *student's Roll Number*:", parse_mode="MarkdownV2")
    return ST_STUDENT_ROLL

# ── Student roll ──────────────────────────────────────────────────
async def student_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(context)
    session["student_roll"] = update.message.text.strip()
    session["scores"]       = {}
    session["current_sec"]  = 0

    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Correct — Start Scoring", callback_data="confirm_student"),
        InlineKeyboardButton("✏️ Edit", callback_data="edit_student"),
    ]])
    await update.message.reply_text(
        f"📋 *Confirm Student Details*\n\n"
        f"Name: *{session['student_name']}*\n"
        f"Roll: *{session['student_roll']}*",
        parse_mode="MarkdownV2", reply_markup=kbd
    )
    return ST_SCORING

async def confirm_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_section(query, context, 0)
    return ST_SCORING

async def edit_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the *student's full name* again:", parse_mode="MarkdownV2")
    return ST_STUDENT_NAME

# ── Show section ──────────────────────────────────────────────────
async def show_section(query_or_msg, context, idx):
    session = get_session(context)
    session["current_sec"] = idx
    sec_name = SECTIONS[idx]
    existing = session["scores"].get(idx)
    note = f"\n_Current: {existing}/5_" if existing is not None else ""
    text = (
        f"📋 *Section {idx+1} of {len(SECTIONS)}*\n"
        f"*{sec_name}*{note}\n\n"
        f"Select score \\(0–5\\):"
    )
    kbd = scores_keyboard(idx)
    if hasattr(query_or_msg, "edit_message_text"):
        await query_or_msg.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd)
    else:
        await query_or_msg.reply_text(text, parse_mode="MarkdownV2", reply_markup=kbd)

# ── Score callback ────────────────────────────────────────────────
async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, idx_str, score_str = query.data.split("|")
    idx   = int(idx_str)
    score = int(score_str)
    session = get_session(context)
    session["scores"][idx] = score

    if idx + 1 < len(SECTIONS):
        await show_section(query, context, idx + 1)
        return ST_SCORING
    else:
        await show_summary(query, context)
        return ST_SUMMARY

async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    session = get_session(context)
    session["scores"].pop(idx, None)   # ensure it's None / absent

    if idx + 1 < len(SECTIONS):
        await show_section(query, context, idx + 1)
        return ST_SCORING
    else:
        await show_summary(query, context)
        return ST_SUMMARY

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    if idx == 0:
        # Back to roll number entry
        session = get_session(context)
        await query.edit_message_text(
            f"Please re\\-enter the *student's Roll Number*:", parse_mode="MarkdownV2"
        )
        return ST_STUDENT_ROLL
    await show_section(query, context, idx - 1)
    return ST_SCORING

# ── Summary ───────────────────────────────────────────────────────
async def show_summary(query, context):
    session = get_session(context)
    scored = [v for v in session["scores"].values() if v is not None]
    if not scored:
        await query.edit_message_text(
            "⚠️ You haven't scored any section\\. Please score at least one section\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Start Again", callback_data="restart_scoring")
            ]])
        )
        return

    text = summary_text(session)
    kbd  = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit a Section", callback_data="edit_section"),
         InlineKeyboardButton("✅ Confirm & Submit", callback_data="confirm_submit")]
    ])
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd)

async def restart_scoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session(context)
    session["scores"] = {}
    await show_section(query, context, 0)
    return ST_SCORING

# ── Edit section ──────────────────────────────────────────────────
async def edit_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session(context)
    await query.edit_message_text(
        "✏️ *Which section do you want to edit?*",
        parse_mode="MarkdownV2",
        reply_markup=edit_sections_keyboard(session["scores"])
    )
    return ST_EDIT_SECTION

async def edit_sec_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("|")[1])
    await show_section(query, context, idx)
    return ST_SCORING

async def edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_summary(query, context)
    return ST_SUMMARY

# ── Remark ────────────────────────────────────────────────────────
async def ask_remark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 *Enter your Remark* for this student:\n_\\(Text only — no scores\\)_",
        parse_mode="MarkdownV2"
    )
    return ST_REMARK

async def receive_remark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(context)
    remark  = update.message.text.strip()
    if any(char.isdigit() for char in remark) and len(remark) < 5:
        await update.message.reply_text("⚠️ Please enter a descriptive text remark, not just a number.")
        return ST_REMARK
    session["remark"] = remark

    # Save to DB
    iv_key   = session["interviewer_key"]
    iv_name  = session["interviewer_name"]
    s_name   = session["student_name"]
    s_roll   = session["student_roll"]
    scores   = session["scores"]
    date_str = datetime.now().strftime("%d %b %Y")

    db.save_report(s_roll, s_name, date_str, iv_key, iv_name, scores, remark)

    # After submit options
    kbd = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ More Interviewers Will Submit", callback_data="more_ivs")],
        [InlineKeyboardButton("📊 Generate Final Report Now",    callback_data="gen_report")],
    ])
    total_scored = sum(v for v in scores.values() if v is not None)
    await update.message.reply_text(
        f"✅ *Report submitted\\!*\n"
        f"_{iv_name}_ → _{s_name}_ | Roll: _{s_roll}_\n"
        f"Your total: *{total_scored}/50*\n\n"
        f"What next?",
        parse_mode="MarkdownV2", reply_markup=kbd
    )
    return ST_AFTER_SUBMIT

# ── After submit ──────────────────────────────────────────────────
async def more_interviewers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session(context)
    s_name = session["student_name"]
    s_roll = session["student_roll"]
    await query.edit_message_text(
        f"⏳ *Waiting for more evaluators*\n\n"
        f"The next interviewer should open the bot on their Telegram and submit "
        f"their report for:\n\n"
        f"👤 *{s_name}* | Roll: *{s_roll}*",
        parse_mode="MarkdownV2"
    )
    return ConversationHandler.END

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session  = get_session(context)
    s_name   = session["student_name"]
    s_roll   = session["student_roll"]

    reports = db.get_reports(s_roll)
    if len(reports) < 2:
        await query.edit_message_text(
            "⚠️ *Minimum 2 evaluators required\\.*\n"
            "Please have another interviewer submit first\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Try Again", callback_data="gen_report")
            ]])
        )
        return ST_AFTER_SUBMIT

    await query.edit_message_text("⏳ Generating report\\.\\.\\.", parse_mode="MarkdownV2")

    report_data = db.compile_report(s_roll)
    date_str    = report_data["date"]

    # Send to interviewer
    pdf_path = await send_report(
        query.get_bot(), query.message.chat_id,
        s_name, s_roll, report_data, date_str
    )

    # Send to group
    try:
        await send_report(
            query.get_bot(), GROUP_ID,
            s_name, s_roll, report_data, date_str
        )
    except Exception as e:
        logger.error(f"Group send failed: {e}")

    # Fresh start button
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Start New Evaluation", callback_data="new_eval")
    ]])
    await query.get_bot().send_message(
        chat_id=query.message.chat_id,
        text="✅ *Report sent successfully\\!*",
        parse_mode="MarkdownV2",
        reply_markup=kbd
    )
    return ST_AFTER_SUBMIT

async def new_eval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reset_session(context)
    kbd = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💼 Ravi Sir",    callback_data="iv|ravi")],
        [InlineKeyboardButton("👩‍💼 Nikki Ma'am", callback_data="iv|nikki")],
        [InlineKeyboardButton("👨‍💼 Amit Sir",    callback_data="iv|amit")],
        [InlineKeyboardButton("👩‍💼 Raksha Ma'am",callback_data="iv|raksha")],
    ])
    await query.edit_message_text(
        "🙏 *Welcome to Pareeksha Gurukul*\n_IB SA Mock Interview Evaluation_\n\nPlease select your name:",
        parse_mode="MarkdownV2", reply_markup=kbd
    )
    return ST_SELECT_INTERVIEWER

# ══════════════════════════════════════════════════════════════════
# /download command
# ══════════════════════════════════════════════════════════════════
async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Search Report*\n\nEnter student name or roll number:",
        parse_mode="MarkdownV2"
    )
    return ST_DOWNLOAD_QUERY

async def download_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    results    = db.search_student(query_text)

    if not results:
        await update.message.reply_text(
            f"❌ No report found for *{query_text}*\\.\n"
            f"Please check the name or roll number and try again\\.",
            parse_mode="MarkdownV2"
        )
        return ST_DOWNLOAD_QUERY

    if len(results) == 1:
        r = results[0]
        context.user_data["dl_roll"] = r["roll"]
        await send_download(update, context, r["roll"], r["name"])
        return ConversationHandler.END

    # Multiple results
    btns = [[InlineKeyboardButton(
        f"{r['name']} — {r['roll']}", callback_data=f"dl|{r['roll']}"
    )] for r in results]
    await update.message.reply_text(
        "📁 *Multiple records found\\. Select one:*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(btns)
    )
    return ST_DOWNLOAD_SELECT

async def download_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    roll = query.data.split("|")[1]
    report_data = db.compile_report(roll)
    if not report_data:
        await query.edit_message_text("❌ Report not found.")
        return ConversationHandler.END
    await query.edit_message_text("⏳ Fetching your report...")
    await send_download(query, context, roll, report_data["student_name"])
    return ConversationHandler.END

async def send_download(update_or_query, context, roll, name):
    report_data = db.compile_report(roll)
    if not report_data:
        return
    chat_id  = update_or_query.effective_chat.id if hasattr(update_or_query, "effective_chat") else update_or_query.message.chat_id
    bot      = context.bot
    pdf_path = generate_pdf(name, roll, report_data["date"], report_data)
    with open(pdf_path, "rb") as f:
        await bot.send_document(
            chat_id=chat_id, document=f,
            filename=f"Interview_Report_{roll}.pdf",
            caption=f"📄 Report for *{name}* | Roll: {roll}",
            parse_mode="Markdown"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    await update.message.reply_text("❌ Cancelled. Send /start to begin again.")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    main_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ST_SELECT_INTERVIEWER: [
                CallbackQueryHandler(select_interviewer, pattern="^iv\\|"),
            ],
            ST_STUDENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_name),
            ],
            ST_STUDENT_ROLL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_roll),
            ],
            ST_SCORING: [
                CallbackQueryHandler(confirm_student,  pattern="^confirm_student$"),
                CallbackQueryHandler(edit_student,     pattern="^edit_student$"),
                CallbackQueryHandler(handle_score,     pattern="^score\\|"),
                CallbackQueryHandler(handle_skip,      pattern="^skip\\|"),
                CallbackQueryHandler(handle_back,      pattern="^back\\|"),
                CallbackQueryHandler(restart_scoring,  pattern="^restart_scoring$"),
            ],
            ST_SUMMARY: [
                CallbackQueryHandler(edit_section,     pattern="^edit_section$"),
                CallbackQueryHandler(ask_remark,       pattern="^confirm_submit$"),
            ],
            ST_EDIT_SECTION: [
                CallbackQueryHandler(edit_sec_select,  pattern="^edit_sec\\|"),
                CallbackQueryHandler(edit_done,        pattern="^edit_done$"),
            ],
            ST_REMARK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remark),
            ],
            ST_AFTER_SUBMIT: [
                CallbackQueryHandler(more_interviewers, pattern="^more_ivs$"),
                CallbackQueryHandler(generate_report,   pattern="^gen_report$"),
                CallbackQueryHandler(new_eval,          pattern="^new_eval$"),
                CallbackQueryHandler(select_interviewer,pattern="^iv\\|"),
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
            ST_DOWNLOAD_SELECT: [CallbackQueryHandler(download_select, pattern="^dl\\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False,
        allow_reentry=True,
    )

    app.add_handler(main_conv)
    app.add_handler(dl_conv)

    logger.info("Bot started (polling)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
