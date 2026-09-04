from channels.layers import get_channel_layer
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from database.db_manager import db
from config.settings import build_miniapp_url
from workspace.sqlite_payloads import message_payload

channel_layer = get_channel_layer()


def legacy_reply_keyboard(student_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Reply", callback_data=f"legacy_reply:{student_id}")],
        ],
    )


async def broadcast_to_teacher(teacher_id: int, message_id: int):
    row = db.get_message_by_id(message_id)
    if not row:
        return
    await channel_layer.group_send(
        f"teacher_{teacher_id}",
        {
            "type": "ws.message",
            "payload": {
                "type": "chat.message",
                "message": message_payload(row, teacher_id),
            },
        },
    )


def student_chat_button(student_id: int):
    miniapp_url = build_miniapp_url(f"chat_{student_id}")
    if not miniapp_url:
        return None
    return InlineKeyboardButton(
        text="Відкрити чат",
        web_app=WebAppInfo(url=miniapp_url),
    )


def teacher_notification_markup(student_id: int):
    rows = [[InlineKeyboardButton(text="Reply", callback_data=f"legacy_reply:{student_id}")]]
    button = student_chat_button(student_id)
    if button:
        rows.append([button])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_student_pm_splitter(message, bot, teacher_id: int):
    """
    aiogram 3 variant of the parallel flow:
    1. Keep legacy inline Reply button.
    2. Save to the existing SQLite DB.
    3. Push to Django Channels.
    """
    student_id = message.from_user.id

    if message.text:
        forwarded = await bot.send_message(
            chat_id=teacher_id,
            text=f"👨‍🎓 {message.from_user.full_name}\n\n{message.text}",
            reply_markup=teacher_notification_markup(student_id),
        )
        message_id = db.save_message(
            from_user_id=student_id,
            to_user_id=teacher_id,
            group_id=None,
            message_text=message.text,
            message_type="text",
            file_id=None,
        )
    elif message.voice:
        forwarded = await bot.send_voice(
            chat_id=teacher_id,
            voice=message.voice.file_id,
            caption=f"👨‍🎓 {message.from_user.full_name}",
            reply_markup=teacher_notification_markup(student_id),
        )
        message_id = db.save_message(
            from_user_id=student_id,
            to_user_id=teacher_id,
            group_id=None,
            message_text="",
            message_type="voice",
            file_id=message.voice.file_id,
        )
    else:
        return

    db.save_delivery(message_id, student_id, message.message_id)
    db.save_delivery(message_id, teacher_id, forwarded.message_id)
    await broadcast_to_teacher(teacher_id, message_id)


async def send_voice_to_student(bot, student_id: int, voice_path: str):
    return await bot.send_voice(chat_id=student_id, voice=FSInputFile(voice_path))
