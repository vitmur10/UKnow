"""Збір повідомлень про проблеми від усіх ролей."""
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database.db_manager import db

REPORT_CHAT_ID = int(os.getenv("PROBLEM_REPORT_CHAT_ID", "0") or 0)
REPORT_THREAD_ID = int(os.getenv("PROBLEM_REPORT_THREAD_ID", "0") or 0)
REPORT_MENTIONS = "@olesyaa_olesyaa @natalia0542 @v_lhov @anastasiasuntseva @UKnow_Admin_Alynaalyo @UKnow_Admin"


def is_reporting(context):
    return bool(context.user_data.get("problem_report_active"))


async def problem_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["problem_report_active"] = True
    await update.message.reply_text(
        "Опишіть проблему повідомленням або надішліть скріншот/відео. "
        "Можна надіслати все разом. Для скасування натисніть /cancel."
    )


def _target_kwargs():
    kwargs = {"chat_id": REPORT_CHAT_ID}
    if REPORT_THREAD_ID:
        kwargs["message_thread_id"] = REPORT_THREAD_ID
    return kwargs


async def problem_report_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_reporting(context):
        return False
    if not REPORT_CHAT_ID:
        await update.effective_message.reply_text("⚠️ Канал повідомлень ще не налаштований адміністратором.")
        context.user_data.pop("problem_report_active", None)
        return True
    user = update.effective_user
    header = f"🚨 <b>Повідомлення про проблему</b>\n👤 {user.full_name} (@{user.username or 'без username'})\n🆔 <code>{user.id}</code>\n\n{REPORT_MENTIONS}"
    try:
        target = _target_kwargs()
        if update.message.text:
            sent = await context.bot.send_message(**target, text=header + "\n\n" + update.message.text, parse_mode=ParseMode.HTML)
            db.save_problem_report_delivery(REPORT_CHAT_ID, REPORT_THREAD_ID or None, sent.message_id, user.id)
        else:
            sent = await context.bot.send_message(**target, text=header, parse_mode=ParseMode.HTML)
            copied = await update.message.copy(chat_id=REPORT_CHAT_ID, message_thread_id=REPORT_THREAD_ID or None)
            db.save_problem_report_delivery(REPORT_CHAT_ID, REPORT_THREAD_ID or None, sent.message_id, user.id)
            db.save_problem_report_delivery(REPORT_CHAT_ID, REPORT_THREAD_ID or None, copied.message_id, user.id)
        await update.effective_message.reply_text("✅ Повідомлення передано адміністраторам.")
    except Exception as exc:
        await update.effective_message.reply_text("❌ Не вдалося передати повідомлення. Спробуйте ще раз.")
        print(f"[problem_report] {exc}")
    context.user_data.pop("problem_report_active", None)
    return True


async def problem_report_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward a staff reply in the report topic back to the reporter."""
    message = update.effective_message
    chat = update.effective_chat
    reply = message.reply_to_message if message else None
    if not message or not chat or not reply:
        return
    if chat.id != REPORT_CHAT_ID:
        return
    thread_id = getattr(message, "message_thread_id", None)
    if REPORT_THREAD_ID and thread_id != REPORT_THREAD_ID:
        return
    sender = update.effective_user
    staff = db.get_user(sender.id) if sender else None
    if not staff or staff[4] not in ("admin", "teacher"):
        return
    recipient_id = db.find_problem_report_user(chat.id, thread_id, reply.message_id)
    if not recipient_id:
        return
    try:
        if message.text:
            await context.bot.send_message(
                chat_id=recipient_id,
                text=f"💬 Відповідь адміністрації щодо вашого повідомлення:\n\n{message.text}",
            )
        else:
            await context.bot.send_message(
                chat_id=recipient_id,
                text="💬 Відповідь адміністрації щодо вашого повідомлення:",
            )
            await message.copy(chat_id=recipient_id)
        await message.reply_text("✅ Відповідь надіслано автору повідомлення.")
    except Exception as exc:
        print(f"[problem_report] reply delivery failed for {recipient_id}: {exc}")


async def problem_report_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("problem_report_active", None)
    await update.message.reply_text("Скасовано.")


async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    thread_id = getattr(update.message, "message_thread_id", None)
    await update.message.reply_text(f"Chat ID: `{chat.id}`\nThread ID: `{thread_id or 'не визначено'}`", parse_mode=ParseMode.MARKDOWN)
