# -*- coding: utf-8 -*-
"""
handlers/chat_engine.py — двигун P2P-чатів (учень ↔ викладач ↔ група).

РЕФАКТОРИНГ:
1. Чат більше НЕ використовує ConversationHandler. Активний стан зберігається
   у context.user_data (ключі chat_kind / chat_peer_id / chat_role) і
   перевіряється у глобальних обробниках (main.py -> global_message_handler,
   global_media_handler). Користувач ніколи не "застрягає" у стані.
2. Повідомлення (текст і медіа) пересилаються МИТТЄВО через copy_message /
   send_message — без буферизації з asyncio.sleep, тому нічого не губиться.
   Кожен файл альбому зберігається в БД окремо і доставляється одразу.
3. Прибрано всі системні відбивки "✅ Повідомлення відправлено" тощо.
4. При старті чату надсилається і ЗАКРІПЛЮЄТЬСЯ сервісне повідомлення
   "💬 Ви зараз спілкуєтесь з ..." (bot.pin_chat_message).
5. Історія: пагінація по 6 реплік з кнопками ⬅️/➡️ (див. common.show_chat_page)
   + вивантаження історії у .txt файл (export_chat_history_file).
"""

import html
import io
import sqlite3

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import ContextTypes

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_chat_active_keyboard
from utils.helpers import is_lesson_link
from config.settings import (
    now_kyiv_str, now_kyiv, ALL_MAIN_MENU_BUTTONS_LIST,
)

# ==========================================================================
# СТАН АКТИВНОГО ЧАТУ (context.user_data)
# ==========================================================================

# Всі ключі, що стосуються чату (включно з legacy-ключами старої версії)
_CHAT_STATE_KEYS = [
    'chat_kind', 'chat_peer_id', 'chat_role', 'chat_pinned_msg_id',
    # legacy — чистимо, щоб старі "зависли" стани не заважали
    'chat_type', 'chat_with', 'chat_with_group',
    'student_chat_type', 'student_chat_with', 'student_chat_with_group',
    'teacher_chat_type', 'teacher_chat_with', 'teacher_chat_with_group',
]

# Захист від повторного заголовка для одного альбому: media_group_id -> True
_album_header_sent: dict = {}


def get_active_chat(context: ContextTypes.DEFAULT_TYPE):
    """Повертає dict з активним чатом або None."""
    kind = context.user_data.get('chat_kind')
    peer_id = context.user_data.get('chat_peer_id')
    if not kind or not peer_id:
        return None
    return {
        'kind': kind,                                   # 'individual' | 'group'
        'peer_id': peer_id,                             # user_id або group_id
        'role': context.user_data.get('chat_role', 'student'),
    }


def _clear_chat_state(context: ContextTypes.DEFAULT_TYPE):
    for key in _CHAT_STATE_KEYS:
        context.user_data.pop(key, None)


async def _unpin_service_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Відкріплює сервісне повідомлення чату, якщо воно було закріплене."""
    pinned_id = context.user_data.get('chat_pinned_msg_id')
    if pinned_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=pinned_id)
        except Exception as e:
            print(f"[chat] unpin error: {e}")
    context.user_data.pop('chat_pinned_msg_id', None)


async def start_chat_session(context: ContextTypes.DEFAULT_TYPE, user_id: int,
                             role: str, kind: str, peer_id: int):
    """
    Активує чат для user_id, надсилає та ЗАКРІПЛЮЄ сервісне повідомлення
    "💬 Ви зараз спілкуєтесь з ...".
    """
    # Прибираємо попереднє закріплення (якщо було)
    await _unpin_service_message(context, user_id)
    _clear_chat_state(context)

    context.user_data['chat_kind'] = kind
    context.user_data['chat_peer_id'] = peer_id
    context.user_data['chat_role'] = role

    # Текст сервісного повідомлення
    if kind == 'group':
        group = db.get_group_by_id(peer_id)
        peer_name = html.escape(group[1]) if group else "Невідома група"
        text = f"💬 Ви зараз спілкуєтесь з групою: <b>{peer_name}</b>"
    else:
        peer = db.get_user(peer_id)
        peer_name = html.escape(f"{peer[2]} {peer[3]}") if peer else "Невідомо"
        who = "учнем" if role == 'teacher' else "викладачем"
        text = f"💬 Ви зараз спілкуєтесь з {who}: <b>{peer_name}</b>"

    text += ("\n\n<i>Щоб видалити своє повідомлення у всіх — зробіть на нього "
             "reply (відповісти) з командою /del</i>")

    try:
        service_msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode='HTML',
            reply_markup=get_chat_active_keyboard()
        )
        context.user_data['chat_pinned_msg_id'] = service_msg.message_id
        try:
            await context.bot.pin_chat_message(
                chat_id=user_id,
                message_id=service_msg.message_id,
                disable_notification=True
            )
        except Exception as pin_err:
            print(f"[chat] pin error: {pin_err}")
    except Exception as e:
        print(f"[chat] start session error: {e}")


async def end_chat_session(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Тихо завершує чат: відкріплення, очищення стану, скасування таймера."""
    _cancel_auto_end(context, chat_id)
    await _unpin_service_message(context, chat_id)
    _clear_chat_state(context)


# ==========================================================================
# АВТО-ЗАВЕРШЕННЯ ВИДАЛЕНО (фідбек користувачів: повідомлення про 5 хв
# бездіяльності — зайве). Закріплене сервісне повідомлення завжди показує,
# з ким триває діалог, тому таймер не потрібен. Чат закривається кнопкою
# "Завершити діалог" або будь-якою кнопкою головного меню.
# Прибираємо застарілі job-и попередньої версії, якщо вони ще у черзі.
# ==========================================================================

def _cancel_auto_end(context, chat_id: int):
    """Скасовує застарілі таймери авто-завершення (сумісність зі старою версією)."""
    try:
        for job in context.job_queue.get_jobs_by_name(f"auto_end_{chat_id}"):
            job.schedule_removal()
    except Exception:
        pass


# ==========================================================================
# ЗАВЕРШЕННЯ ЧАТУ КОРИСТУВАЧЕМ
# ==========================================================================

async def chat_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Завершити діалог 🔚' — тихо закриває чат і повертає меню."""
    user_id = update.effective_user.id
    await end_chat_session(context, user_id)

    user = db.get_user(user_id)
    role = user[4] if user else 'student'
    await update.message.reply_text("Головне меню:", reply_markup=get_main_keyboard(role))


# ==========================================================================
# МАРШРУТИЗАТОР КНОПОК ГОЛОВНОГО МЕНЮ
# ==========================================================================

async def menu_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Єдиний обробник усіх кнопок головного меню.
    Спочатку тихо закриває активний чат (якщо був), потім викликає потрібну функцію.
    """
    text = update.message.text
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Спочатку зареєструйтеся за допомогою команди /start")
        return

    role = user[4]

    # Тихо закриваємо активний чат
    if get_active_chat(context):
        await end_chat_session(context, user_id)

    # Чистимо "залиплі" прапорці очікування вводу (дата/пошук в історії),
    # щоб користувач не отримував "Неправильний формат дати" на кнопки меню
    context.user_data.pop('waiting_for_date', None)
    context.user_data.pop('waiting_for_search_name', None)
    context.user_data.pop('search_chat_type', None)

    # Захист адмін-кнопок
    admin_buttons = ["👨‍💼 Керування користувачами", "👥 Керування групами", "🗓 Керування розкладом",
                     "🗂️ Переписки / Чати", "📢 Масова розсилка", "📊 Звіти"]
    if text in admin_buttons and role != 'admin':
        await update.message.reply_text("❌ У вас немає прав доступу до цієї функції.")
        return

    # Словник-маршрутизатор: Кнопка -> (Модуль, Функція)
    routes = {
        '💬 Написати викладачеві/групі': ('handlers.chat_engine', 'student_message_start'),
        '💬 Написати учневі/групі': ('handlers.chat_engine', 'teacher_message_students'),
        '🏫 Про школу': ('handlers.student', 'menu_about_school'),
        '📋 Правила школи': ('handlers.student', 'menu_school_rules'),
        '❓ Популярні питання': ('handlers.student', 'menu_faq'),
        '🗓 Мій календар': ('handlers.student', 'menu_student_calendar'),
        '📖 Історія переписок': ('handlers.common', 'handle_history_button'),
        '📆 Мій розклад': ('handlers.teacher', 'menu_teacher_schedule'),
        '👨‍🎓 Мої учні': ('handlers.teacher', 'menu_teacher_students'),
        '📚 Мої групи': ('handlers.teacher', 'show_teacher_groups'),
        '📊 Статистика': ('handlers.teacher', 'menu_teacher_stats'),
        '📬 Вхідні': ('handlers.teacher', 'teacher_inbox'),
        '👥 Керування групами': ('handlers.admin', 'menu_admin_groups'),
        '🗂️ Переписки / Чати': ('handlers.admin', 'menu_admin_chats'),
        '🗓 Керування розкладом': ('handlers.admin', 'menu_admin_schedule'),
        '👨‍💼 Керування користувачами': ('handlers.admin', 'menu_admin_users'),
        '📊 Звіти': ('handlers.admin', 'menu_admin_reports'),
        '📞 Написати менеджеру': ('handlers.common', 'route_manager_contact'),
    }

    if text in routes:
        module_name, func_name = routes[text]
        import importlib
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        await func(update, context)
    else:
        await update.message.reply_text("Оберіть дію:", reply_markup=get_main_keyboard(role))


# ==========================================================================
# ВИБІР СПІВРОЗМОВНИКА (точки входу)
# ==========================================================================

async def student_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує учневі список викладачів та груп для чату."""
    user_id = update.effective_user.id

    teacher = db.get_student_teacher(user_id)
    groups = db.get_student_groups(user_id)

    keyboard = []

    if teacher:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🏫 {teacher[2]} {teacher[3]}",
            callback_data=f"student_chat_teacher_{teacher[0]}"
        )])

    for group in groups or []:
        keyboard.append([InlineKeyboardButton(
            f"👥 Група '{group[1]}'",
            callback_data=f"student_chat_group_{group[0]}"
        )])

    if not teacher and not groups:
        await update.message.reply_text(
            "На жаль, у вас немає призначеного викладача або групи для початку діалогу.")
        return

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_student_chat")])

    await update.message.reply_text(
        "Оберіть співрозмовника:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def teacher_message_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує викладачеві список учнів та груп для чату."""
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user or user[4] != 'teacher':
        await update.message.reply_text("Ця функція доступна лише викладачам.")
        return

    students = db.get_teacher_students(user_id)
    groups = db.get_teacher_groups(user_id)

    if not students and not groups:
        await update.message.reply_text("У вас ще немає учнів та груп.")
        return

    keyboard = []

    for student in students:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🎓 {student[2]} {student[3]} (індивідуально)",
            callback_data=f"teacher_chat_student_{student[0]}"
        )])

    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"👥 {group[1]} ({group[3]})",
            callback_data=f"teacher_chat_group_{group[0]}"
        )])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_teacher_chat")])

    await update.message.reply_text(
        "💬 Кому хочете написати?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def teacher_quick_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка ↩️ Відповісти у Вхідних викладача (inbox_reply_<student_id>)."""
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    student_id = int(query.data.split("_")[2])

    student = db.get_user(student_id)
    if not student:
        await query.answer("❌ Учня не знайдено.", show_alert=True)
        return

    db.mark_messages_read(from_user_id=student_id, to_user_id=teacher_id)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await start_chat_session(context, teacher_id, 'teacher', 'individual', student_id)


async def quick_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Швидка відповідь по кнопці під повідомленням:
      quick_reply_teacher_<teacher_id> — відповідь викладачеві
      quick_reply_group_<group_id>    — відповідь у групу
    Працює для будь-якої ролі (роль визначаємо з БД).
    """
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = db.get_user(user_id)
    role = user[4] if user else 'student'

    parts = query.data.split("_")  # ['quick','reply','teacher','12345']
    reply_type = parts[2]
    target_id = int(parts[3])

    if reply_type == "teacher":
        if not db.get_user(target_id):
            await query.answer("❌ Викладача не знайдено.", show_alert=True)
            return
        kind, peer_id = 'individual', target_id
    else:
        if not db.get_group_by_id(target_id):
            await query.answer("❌ Групу не знайдено.", show_alert=True)
            return
        kind, peer_id = 'group', target_id

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await start_chat_session(context, user_id, role, kind, peer_id)


# ==========================================================================
# ПЕРЕСИЛАННЯ ПОВІДОМЛЕНЬ (єдиний двигун для тексту і медіа)
# ==========================================================================

def _detect_media(msg):
    """Повертає (media_type, file_id) або ('text', None)."""
    if msg.photo:
        return 'photo', msg.photo[-1].file_id
    if msg.document:
        return 'document', msg.document.file_id
    if msg.video:
        return 'video', msg.video.file_id
    if msg.audio:
        return 'audio', msg.audio.file_id
    if msg.voice:
        return 'voice', msg.voice.file_id
    if msg.video_note:
        return 'video_note', msg.video_note.file_id
    if msg.animation:
        return 'animation', msg.animation.file_id
    if msg.sticker:
        return 'sticker', msg.sticker.file_id
    return 'text', None


def _build_reply_markup(sender_role: str, sender_id: int, kind: str, peer_id: int,
                        sender_first_name: str, group_name: str):
    """Кнопка '↩️ Відповісти' для отримувача."""
    if kind == 'group':
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти в групу {group_name}",
                callback_data=f"quick_reply_group_{peer_id}"
            )
        ]])
    if sender_role == 'teacher':
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти {sender_first_name}",
                callback_data=f"quick_reply_teacher_{sender_id}"
            )
        ]])
    # відправник — учень, отримувач — викладач
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"↩️ Відповісти {sender_first_name}",
            callback_data=f"inbox_reply_{sender_id}"
        )
    ]])


async def relay_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Миттєво пересилає повідомлення (текст/медіа/альбом/стікер) отримувачам
    активного чату. Повертає True, якщо повідомлення оброблено.

    Без буферизації і без відбивок відправнику — як звичайний месенджер.
    """
    state = get_active_chat(context)
    if not state:
        return False

    msg = update.message
    sender_id = update.effective_user.id
    sender = db.get_user(sender_id)
    if not sender:
        return False

    sender_role = state['role']
    kind = state['kind']
    peer_id = state['peer_id']
    sender_full_name = f"{sender[2]} {sender[3]}"
    safe_sender = html.escape(sender_full_name)

    # --- Отримувачі ---
    recipients = set()
    group_id_for_db = None
    to_user_id_for_db = None
    group_name = ""

    if kind == 'individual':
        to_user_id_for_db = peer_id
        recipients.add(peer_id)
    else:
        group_info = db.get_group_by_id(peer_id)
        if not group_info:
            await msg.reply_text("❌ Групу не знайдено. Діалог закрито.")
            await end_chat_session(context, sender_id)
            return True
        group_id_for_db = peer_id
        group_name = group_info[1]
        for m in db.get_group_members(peer_id):
            recipients.add(m[0])
        if group_info[2]:
            recipients.add(group_info[2])  # викладач групи

    recipients.discard(sender_id)

    if not recipients:
        await msg.reply_text("❌ Не вдалося визначити отримувача.")
        return True

    # --- Вміст ---
    media_type, file_id = _detect_media(msg)
    content_text = (msg.text or msg.caption or "").strip()

    if media_type == 'sticker':
        emoji = msg.sticker.emoji or ""
        set_name = msg.sticker.set_name or ""
        content_text = f"🎭 [Стікер {emoji}] {set_name}".strip()

    if media_type == 'text' and not content_text:
        return True  # порожнє — ігноруємо

    # --- Збереження в БД (кожне повідомлення/файл окремо) ---
    msg_db_id = None
    try:
        msg_db_id = db.save_message(
            from_user_id=sender_id,
            to_user_id=to_user_id_for_db,
            group_id=group_id_for_db,
            message_text=content_text,
            message_type=media_type,
            file_id=file_id
        )
        # Фіксуємо оригінал у чаті відправника (щоб /del міг знайти повідомлення)
        db.save_delivery(msg_db_id, sender_id, msg.message_id)
    except Exception as e:
        print(f"[relay] db save error: {e}")

    # --- Заголовок ---
    now_str = now_kyiv_str()
    if kind == 'group':
        header = f"👥 <b>{html.escape(group_name)}</b> · <b>{safe_sender}</b>  <i>{now_str}</i>"
    else:
        header = f"📩 <b>{safe_sender}</b>  <i>{now_str}</i>"

    # Для альбомів: заголовок і кнопка — лише з першим файлом альбому
    mgid = msg.media_group_id
    is_album_tail = False
    if mgid:
        if mgid in _album_header_sent:
            is_album_tail = True
        else:
            _album_header_sent[mgid] = True
            if len(_album_header_sent) > 300:  # проста профілактика росту
                for old_key in list(_album_header_sent.keys())[:150]:
                    _album_header_sent.pop(old_key, None)

    reply_markup = _build_reply_markup(
        sender_role, sender_id, kind, peer_id,
        sender_full_name.split()[0], group_name
    )

    lesson_link = is_lesson_link(content_text)
    delivered = 0

    for r_id in recipients:
        try:
            if media_type == 'text':
                sent_msg = await context.bot.send_message(
                    chat_id=r_id,
                    text=f"{header}\n\n{html.escape(content_text)}",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                db.save_delivery(msg_db_id, r_id, sent_msg.message_id)
                if lesson_link:
                    try:
                        await context.bot.pin_chat_message(
                            chat_id=r_id, message_id=sent_msg.message_id,
                            disable_notification=True)
                    except Exception as pin_err:
                        print(f"[relay] pin lesson link error: {pin_err}")

            elif media_type in ('photo', 'video', 'document', 'audio', 'animation'):
                if is_album_tail:
                    # Хвіст альбому — копіюємо з оригінальним підписом, без заголовка
                    copied = await context.bot.copy_message(
                        chat_id=r_id,
                        from_chat_id=msg.chat.id,
                        message_id=msg.message_id
                    )
                    db.save_delivery(msg_db_id, r_id, copied.message_id)
                else:
                    caption = header + (f"\n\n{html.escape(content_text)}" if content_text else "")
                    if len(caption) > 1000:
                        caption = caption[:997] + "…"
                    copied = await context.bot.copy_message(
                        chat_id=r_id,
                        from_chat_id=msg.chat.id,
                        message_id=msg.message_id,
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                    db.save_delivery(msg_db_id, r_id, copied.message_id)

            elif media_type == 'sticker':
                header_msg = await context.bot.send_message(
                    chat_id=r_id, text=header, parse_mode='HTML',
                    reply_markup=reply_markup)
                sticker_msg = await context.bot.send_sticker(chat_id=r_id, sticker=msg.sticker.file_id)
                db.save_delivery(msg_db_id, r_id, header_msg.message_id)
                db.save_delivery(msg_db_id, r_id, sticker_msg.message_id)

            else:  # voice, video_note — не підтримують caption
                header_msg = await context.bot.send_message(
                    chat_id=r_id, text=header, parse_mode='HTML',
                    reply_markup=reply_markup)
                copied = await context.bot.copy_message(
                    chat_id=r_id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
                db.save_delivery(msg_db_id, r_id, header_msg.message_id)
                db.save_delivery(msg_db_id, r_id, copied.message_id)

            delivered += 1
        except Exception as e:
            print(f"[relay] delivery error to {r_id}: {e}")

    # Повідомляємо відправника ЛИШЕ у разі повної невдачі
    if delivered == 0:
        try:
            await msg.reply_text(
                "❌ Не вдалося доставити повідомлення. Можливо, отримувач заблокував бота.")
        except Exception:
            pass

    return True


# ==========================================================================
# ВИДАЛЕННЯ ПОВІДОМЛЕННЯ "ДЛЯ ВСІХ" (/del у reply на своє повідомлення)
# ==========================================================================

async def delete_for_everyone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /del у відповідь (reply) на власне повідомлення у чаті з ботом.
    Видаляє це повідомлення у відправника та в усіх отримувачів
    (Telegram дозволяє видалення протягом 48 годин).
    В БД повідомлення позначається is_deleted=1: зі звичайної історії воно
    зникає, але адміністратор бачить його в архіві з позначкою 🗑.
    """
    user_id = update.effective_user.id
    cmd_msg = update.message
    reply = cmd_msg.reply_to_message

    # Прибираємо саму команду /del, щоб не смітити в чаті
    async def _cleanup_command():
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=cmd_msg.message_id)
        except Exception:
            pass

    if not reply:
        await _cleanup_command()
        await context.bot.send_message(
            chat_id=user_id,
            text="ℹ️ Щоб видалити повідомлення у всіх, зробіть на нього reply "
                 "(відповісти) і надішліть /del")
        return

    found = db.find_message_by_delivery(user_id, reply.message_id)
    if not found:
        await _cleanup_command()
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Це повідомлення не знайдено серед надісланих через бота.")
        return

    msg_db_id, from_user_id = found

    # Видаляти можна лише ВЛАСНІ повідомлення
    if int(from_user_id) != int(user_id):
        await _cleanup_command()
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Видаляти можна лише власні повідомлення.")
        return

    deliveries = db.get_deliveries(msg_db_id)
    failed = 0
    for chat_id, tg_message_id in deliveries:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=tg_message_id)
        except Exception as e:
            failed += 1
            print(f"[del] не вдалося видалити {tg_message_id} у {chat_id}: {e}")

    db.mark_message_deleted(msg_db_id)
    await _cleanup_command()

    if failed:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Повідомлення видалено, але не скрізь: Telegram дозволяє "
                 "видалення лише протягом 48 годин після надсилання.")


# ==========================================================================
# ЕКСПОРТ ІСТОРІЇ У ФАЙЛ (.txt)
# ==========================================================================

def _msg_sender_name(msg_row) -> str:
    """Ім'я відправника — завжди останні дві колонки після JOIN з users."""
    try:
        first = msg_row[-2] or ""
        last = msg_row[-1] or ""
        name = f"{first} {last}".strip()
        return name or "Невідомо"
    except Exception:
        return "Невідомо"


def build_history_txt(messages: list, title: str) -> bytes:
    """
    Формує вміст .txt файлу з історією листування.
    messages — рядки з таблиці messages (JOIN users), відсортовані DESC.
    """
    buf = io.StringIO()
    buf.write(f"{title}\n")
    buf.write(f"Вивантажено: {now_kyiv().strftime('%d.%m.%Y %H:%M')}\n")
    buf.write(f"Всього повідомлень: {len(messages)}\n")
    buf.write("=" * 50 + "\n\n")

    type_labels = {
        'photo': '[Фото]', 'document': '[Документ]', 'audio': '[Аудіо]',
        'video': '[Відео]', 'voice': '[Голосове]', 'video_note': '[Відеоповідомлення]',
        'animation': '[GIF]', 'sticker': '[Стікер]', 'media': '[Медіа]',
    }

    # У БД повідомлення відсортовані DESC — розвертаємо у хронологічний порядок
    for m in reversed(messages):
        text = (m[4] or "").strip()
        m_type = m[5] if len(m) > 5 else 'text'
        timestamp = str(m[6])[:16] if len(m) > 6 and m[6] else "—"
        sender = _msg_sender_name(m)

        label = type_labels.get(m_type, "")
        line_text = f"{label} {text}".strip() if label else (text or "—")

        buf.write(f"[{timestamp}] {sender}:\n{line_text}\n\n")

    return buf.getvalue().encode('utf-8-sig')


async def export_chat_history_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Надсилає .txt файл з історією поточного відкритого чату
    (context.user_data['current_chat_messages']) через send_document.
    """
    query = update.callback_query
    messages = context.user_data.get('current_chat_messages', [])
    title = context.user_data.get('current_chat_title', 'Історія переписки')

    if not messages:
        await query.answer("Немає повідомлень для вивантаження.", show_alert=True)
        return

    await query.answer()

    file_bytes = build_history_txt(messages, title)
    filename = f"chat_history_{now_kyiv().strftime('%Y-%m-%d_%H-%M')}.txt"

    try:
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=InputFile(io.BytesIO(file_bytes), filename=filename),
            caption=f"📥 {title}"
        )
    except Exception as e:
        print(f"[export] send_document error: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Не вдалося сформувати файл історії."
        )


# ==========================================================================
# CALLBACK-РОУТЕР ЧАТІВ (списки, історія, старт чатів)
# ==========================================================================

async def chat_engine_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    user = db.get_user(user_id)
    user_role = user[4] if user else 'student'

    # --- ЕКСПОРТ ІСТОРІЇ У ФАЙЛ ---
    if data == "export_chat_current":
        await export_chat_history_file(update, context)
        return

    await query.answer()

    # --- СТАРТ ЧАТІВ (нова логіка: user_data + pin, без ConversationHandler) ---
    if data.startswith("teacher_chat_student_"):
        student_id = int(data.split("_")[3])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, 'teacher', 'individual', student_id)
        return

    elif data.startswith("teacher_chat_group_"):
        group_id = int(data.split("_")[3])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, 'teacher', 'group', group_id)
        return

    elif data.startswith("student_chat_teacher_"):
        teacher_id = int(data.split("_")[3])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, 'student', 'individual', teacher_id)
        return

    elif data.startswith("student_chat_group_"):
        group_id = int(data.split("_")[3])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, 'student', 'group', group_id)
        return

    # Legacy-старт (використовується у деяких списках: chat_teacher_/chat_group_)
    elif data.startswith("chat_teacher_"):
        teacher_id = int(data.split("_")[2])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, user_role, 'individual', teacher_id)
        return

    elif data.startswith("chat_group_"):
        group_id = int(data.split("_")[2])
        try:
            await query.delete_message()
        except Exception:
            pass
        await start_chat_session(context, user_id, user_role, 'group', group_id)
        return

    elif data in ("cancel_chat", "cancel_teacher_chat", "cancel_student_chat"):
        await end_chat_session(context, user_id)
        try:
            await query.edit_message_text("Скасовано.")
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=user_id, text="Оберіть дію:",
            reply_markup=get_main_keyboard(user_role))
        return

    # --- ПАГІНАЦІЯ ІСТОРІЇ: chat_page_<PAGE>_<FILESONLY>_<DELETEDONLY> ---
    elif data.startswith("chat_page_"):
        parts = data.split("_")
        try:
            page_number = int(parts[2])
            files_only = (parts[3] == "1") if len(parts) > 3 else False
            deleted_only = (parts[4] == "1") if len(parts) > 4 else False
            from handlers.common import show_chat_page
            await show_chat_page(query, context, page_number,
                                 files_only=files_only, deleted_only=deleted_only)
        except (IndexError, ValueError) as e:
            print(f"Помилка пагінації чату: {e}")
        return

    # --- СПИСКИ ДЛЯ ПЕРЕГЛЯДУ ІСТОРІЇ (адмін): chat_by_<type>_<page> ---
    elif data.startswith("chat_by_"):
        parts = data.split("_")
        chat_type = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0

        context.user_data['chat_filter_type'] = chat_type
        items_per_page = 10

        if chat_type == "student":
            users = db.get_users_by_role('student')
            users.sort(key=lambda x: (x[2] or "").lower())
            label, prefix, title = "👨‍🎓", "view_chat_student", "Оберіть учня:"
        elif chat_type == "teacher":
            users = db.get_users_by_role('teacher')
            users.sort(key=lambda x: (x[2] or "").lower())
            label, prefix, title = "👨‍🏫", "view_chat_teacher", "Оберіть викладача:"
        elif chat_type == "group":
            users = db.get_all_groups()
            label, prefix, title = "👥", "view_chat_group", "Оберіть групу:"
        else:
            await query.edit_message_text("Введіть дату в форматі ДД.ММ.РРРР:")
            context.user_data['waiting_for_date'] = True
            return

        if not users:
            await query.edit_message_text(f"Немає даних для {chat_type}.")
            return

        total_pages = (len(users) + items_per_page - 1) // items_per_page
        start = page * items_per_page
        end = start + items_per_page
        current_list = users[start:end]

        keyboard = []
        for item in current_list:
            name = item[1] if chat_type == "group" else f"{item[2] or ''} {item[3] or ''}".strip() or "Без імені"
            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{item[0]}")])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_by_{chat_type}_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="ignore"))
        if end < len(users):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"chat_by_{chat_type}_{page + 1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("🔍 Пошук за ім'ям", callback_data=f"search_chat_user_{chat_type}")])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_chat_menu")])

        await query.edit_message_text(
            f"💬 {title}\nСторінка {page + 1} з {total_pages}",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("search_chat_user_"):
        chat_type = data.split("_")[3]
        context.user_data['waiting_for_search_name'] = True
        context.user_data['search_chat_type'] = chat_type
        await query.edit_message_text("🔎 **Введіть ім'я або прізвище (або частину):**", parse_mode="Markdown")
        return

    # --- ПЕРЕГЛЯД КОНКРЕТНОГО ЧАТУ (ІСТОРІЯ) ---
    elif data.startswith("view_chat_"):
        parts = data.split("_")
        messages = []
        title = ""

        entity_type = parts[2]
        entity_id = int(parts[-1])

        # 1. УЧЕНЬ
        if user_role == 'student':
            if "teacher" in data:
                teacher = db.get_user(entity_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=entity_id)
                title = f"👨‍🏫 Чат з викладачем: {teacher[2]} {teacher[3]}"
            elif "group" in data:
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Чат групи: {group_data[1]}"

        # 2. ВИКЛАДАЧ
        elif user_role == 'teacher':
            if "student" in data:
                student = db.get_user(entity_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=entity_id)
                title = f"👨‍🎓 Чат з учнем: {student[2]} {student[3]}"
            elif "group" in data:
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Чат групи: {group_data[1]}"

        # 3. АДМІНІСТРАТОР
        elif user_role == 'admin':
            entity_id = int(parts[3])
            context.user_data['current_chat_entity_id'] = entity_id
            context.user_data['current_chat_entity_type'] = entity_type

            if entity_type == "group":
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id, include_deleted=True)
                title = f"👥 Адмін: Чат групи {group_data[1]}"

            elif entity_type in ("student", "teacher"):
                user_entity = db.get_user(entity_id)
                messages = db.get_chat_history(
                    user1_id=entity_id, user2_id=entity_id,
                    include_deleted=True
                )

                icon = "👨‍🎓" if entity_type == "student" else "👨‍🏫"
                name = f"{user_entity[2]} {user_entity[3]}" if user_entity else f"ID: {entity_id}"
                title = f"{icon} Вся історія: {name}"

        # ОБРОБКА РЕЗУЛЬТАТУ
        if not messages:
            back_call = f"chat_by_{entity_type}_0" if user_role == 'admin' else "back_chat_menu"
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=back_call)]]
            await query.edit_message_text(
                f"{title}\n\n❌ Повідомлень ще немає.",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # ПАГІНАЦІЯ ТА ВИВІД
        context.user_data['current_chat_messages'] = messages
        context.user_data['current_chat_title'] = title
        context.user_data['current_page'] = 0

        from handlers.common import show_chat_page
        await show_chat_page(query, context, 0)
        return

    # --- НАЗАД ДО МЕНЮ ПЕРЕПИСОК ---
    elif data == "back_chat_menu":
        if user_role == 'admin':
            keyboard = [
                [InlineKeyboardButton("👨‍🎓 Учні", callback_data="chat_by_student_0")],
                [InlineKeyboardButton("👨‍🏫 Викладачі", callback_data="chat_by_teacher_0")],
                [InlineKeyboardButton("👥 Групи", callback_data="chat_by_group_0")],
            ]
            await query.edit_message_text(
                "🗂️ Переписки. Оберіть категорію:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            try:
                await query.delete_message()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=user_id,
                text="Оберіть дію:",
                reply_markup=get_main_keyboard(user_role)
            )
        return
