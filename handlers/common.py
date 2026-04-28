from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_calendar_keyboard
from utils.helpers import format_lesson_time
from config.settings import IMAGE_WARNING_FILE_ID, logger

# Імпортуємо функції для перегляду історії
from handlers.teacher import show_teacher_chat_history
from handlers.student import show_student_chat_history

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user

    await update.message.reply_text(
        f"📋 Ваша інформація:\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Ім'я: {user.first_name}\n"
        f"👤 Прізвище: {user.last_name or 'Не вказано'}\n"
        f"📧 Username: @{user.username or 'Не вказано'}"
    )

async def manager_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /manager для быстрого доступа к менеджеру"""
    await send_manager_contact_button(update, context)


async def send_manager_contact_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет кнопку для прямого перехода к чату с менеджером"""
    keyboard = [
        [InlineKeyboardButton("📞 Написати менеджеру", url="https://t.me/UKnow_Online_School")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📞 Зв'язок з менеджером\n\n"
        "Натисніть кнопку нижче щоб відкрити чат з менеджером:",
        reply_markup=reply_markup
    )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await debug_student_lessons(update, context)


async def debug_student_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Функция для отладки - показывает все уроки студента"""
    user_id = update.effective_user.id
    lessons = db.get_student_lessons(user_id)

    if not lessons:
        await update.message.reply_text("DEBUG: У вас нет уроков в базе данных")
    else:
        text = f"DEBUG: Найдено {len(lessons)} уроков:\n\n"
        for i, lesson in enumerate(lessons, 1):
            text += f"{i}. Дата: {lesson[3]}, Время: {lesson[4]}\n"
            text += f"   Викладач: {lesson[6]} {lesson[7]}\n"
            if lesson[2]:  # student_id
                text += "   Тип: Індивідуальний\n"
            else:  # group
                text += f"   Тип: Група {lesson[8] or 'Невідомо'}\n"
            text += "\n"

        # Отправляем по частям если текст слишком длинный
        if len(text) > 4000:
            parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(text)


async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text if update.message.text else "[Медіафайл]"

    # --- 1. ПЕРЕВІРКА НА ПОШУК (ДОДАЄМО ЦЕ) ---
    if context.user_data.get('waiting_for_search_name') and user_message != "[Медіафайл]":
        search_query = user_message.strip().lower()
        chat_type = context.user_data.get('search_chat_type', 'student')

        # Отримуємо користувачів
        users = db.get_users_by_role(chat_type)

        # Шукаємо збіги
        found_users = [
            u for u in users
            if search_query in (u[2] or "").lower() or search_query in (u[3] or "").lower()
        ]

        if not found_users:
            await update.message.reply_text(
                f"❌ Нікого не знайдено за запитом '{user_message}'.\nСпробуйте інше ім'я або натисніть /start для скасування."
            )
            return  # Зупиняємо функцію, щоб не спрацював "Вас ніхто не почув"

        # Формуємо список знайдених
        keyboard = []
        label = "👨‍🎓" if chat_type == "student" else "👨‍🏫"
        prefix = "view_chat_student" if chat_type == "student" else "view_chat_teacher"

        for u in found_users:
            name = f"{u[2] or ''} {u[3] or ''}".strip()
            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{u[0]}")])

        keyboard.append([InlineKeyboardButton("🔙 Назад до списку", callback_data=f"chat_by_{chat_type}_0")])

        await update.message.reply_text(
            f"✅ Знайдено {len(found_users)} осіб за запитом '{user_message}':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Скидаємо прапорець очікування
        context.user_data['waiting_for_search_name'] = False
        return  # Важливо! Виходимо, щоб далі не пішов текст про помилку
    # --- КІНЕЦЬ БЛОКУ ПОШУКУ ---

    # Далі йде ваш стандартний код...
    if user_message.startswith('/') and user_message != "[Медіафайл]":
        response_text = "❌ **Невідома команда.**\n\n"
    else:
        response_text = "👋 **Вас ніхто не почув.**\n\n"

    response_text += (
        "Щоб **написати викладачу** або виконати іншу дію, будь ласка, "
        "натисніть на **Меню (чотири квадратики)** ▣ у полі вводу та оберіть дію.\n\n"
        "Для швидкого зв'язку з адміністратором натисніть на **💬 Написати адміністратору**."
    )

    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=IMAGE_WARNING_FILE_ID,
            caption=response_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Помилка при відправці фото: {e}")
        await update.message.reply_text(response_text, parse_mode='Markdown')


async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 📝 НОВИЙ ТЕКСТ ПОВІДОМЛЕННЯ-ПОПЕРЕДЖЕННЯ
    warning_message = (
        "Привіт! 👋"
        "\n\n Ваше повідомлення не потрапило до викладача."
        "\n ❗️Натисніть на **чотири квадратики** біля поля вводу → оберіть    **«💬 Написати викладачу/групі»** → виберіть групу та надішліть повідомлення ✉️"
    )

    chat_id = update.message.chat_id

    # Надсилаємо фото, використовуючи збережений file_id, та додаємо підпис
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=IMAGE_WARNING_FILE_ID,  # Використовуємо ваш file_id
            caption=warning_message,
            parse_mode=ParseMode.MARKDOWN  # Використовуємо ParseMode.MARKDOWN для жирного шрифту
        )
    except Exception as e:
        logger.error(f"Помилка надсилання фото-попередження: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Невідоме повідомлення! Будь ласка, використовуйте кнопки-підказки.",
            parse_mode=ParseMode.MARKDOWN
        )


async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"File ID вашого фото: {file_id}")


async def handle_history_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_role = db.get_user(user_id)[4]

    if user_role == 'teacher':
        await show_teacher_chat_history(update, context, user_id)
    elif user_role == 'student':
        await show_student_chat_history(update, context, user_id)
    else:
        await update.message.reply_text("Ця функція доступна лише для викладачів та учнів.")


MESSAGES_PER_PAGE = 8


def _build_message_card(msg, entity_type: str, current_user_id: int) -> tuple[str, str | None]:
    """
    Формує текстову «картку» одного повідомлення і повертає (card_text, file_id|None).
    card_text — готовий HTML-блок.
    file_id   — якщо повідомлення має медіафайл, повертаємо його file_id, інакше None.
    """
    # --- Розбираємо поля рядка з БД ---
    # msg tuple: id, from_user_id, to_user_id, group_id, message_text,
    #            message_type, file_id, timestamp, is_read, [first_name, last_name] (JOIN)
    # Але get_chat_history повертає: id(0), from(1), to(2), group(3), text(4),
    #   type(5), file_id(6), timestamp(7), is_read(8), first_name(9), last_name(10)
    msg_text   = (msg[4] or "").strip()
    msg_type   = msg[5] if len(msg) > 5 else "text"
    file_id    = msg[6] if len(msg) > 6 else None
    timestamp  = msg[7] if len(msg) > 7 else ""
    first_name = msg[9] if len(msg) > 9 and msg[9] else ""
    last_name  = msg[10] if len(msg) > 10 and msg[10] else ""
    from_id    = msg[1] if len(msg) > 1 else 0

    # --- Ім'я відправника ---
    sender_name = f"{first_name} {last_name}".strip() or "Невідомо"

    # --- Направлення (ти / співрозмовник) ---
    is_mine = (int(from_id) == int(current_user_id))
    direction = "➡️ Ви" if is_mine else f"⬅️ {sender_name}"

    # --- Часова мітка ---
    try:
        dt_obj = datetime.fromisoformat(str(timestamp))
        dt_corrected = dt_obj + timedelta(hours=2)
        time_str = dt_corrected.strftime("%d.%m %H:%M")
    except Exception:
        time_str = str(timestamp)[:16] if timestamp else "—"

    # --- Тип контенту ---
    TYPE_ICONS = {
        "photo":    "🖼",
        "document": "📄",
        "audio":    "🎵",
        "video":    "🎬",
        "voice":    "🎤",
        "text":     "",
        "trigger":  "⚡",
    }
    type_icon = TYPE_ICONS.get(msg_type, "📎")

    # --- Текст картки ---
    if msg_text:
        safe_text = msg_text[:400] + ("…" if len(msg_text) > 400 else "")
    elif file_id:
        safe_text = f"<i>[{type_icon} медіафайл]</i>"
    else:
        safe_text = "<i>[порожнє]</i>"

    card = (
        f"┌ {direction}  <code>{time_str}</code>\n"
        f"│ {type_icon} {safe_text}\n"
        f"└──────────────\n"
    )
    return card, file_id if file_id else None


async def show_chat_page(query, context, page_number: int, files_only: bool = False):
    """
    Відображає сторінку архіву переписки у форматі карток.
    files_only=True — показує лише повідомлення з медіафайлами.
    """
    bot          = query.message.bot
    current_uid  = query.from_user.id
    all_messages = context.user_data.get('current_chat_messages', [])
    title        = context.user_data.get('current_chat_title', '📜 Архів переписки')
    entity_type  = context.user_data.get('current_chat_entity_type', '')

    # Зберігаємо поточний режим фільтра
    context.user_data['chat_files_only'] = files_only

    # Фільтруємо, якщо треба
    if files_only:
        display_messages = [m for m in all_messages if (len(m) > 6 and m[6])]
    else:
        display_messages = all_messages

    total = len(display_messages)
    total_pages = max(1, (total + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE)
    page_number = max(0, min(page_number, total_pages - 1))

    start = page_number * MESSAGES_PER_PAGE
    page_msgs = display_messages[start: start + MESSAGES_PER_PAGE]

    # --- Формуємо текст сторінки ---
    filter_label = "  |  📂 <b>Тільки файли</b>" if files_only else ""
    header = (
        f"<b>{title}</b>{filter_label}\n"
        f"<i>Сторінка {page_number + 1} / {total_pages}  •  всього: {total}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )

    if not page_msgs:
        body = "❌ <i>Повідомлень не знайдено</i>" if files_only else "❌ <i>Повідомлень ще немає</i>"
    else:
        cards = []
        for msg in page_msgs:
            card, _ = _build_message_card(msg, entity_type, current_uid)
            cards.append(card)
        body = "\n".join(cards)

    text = header + body

    # --- Збираємо file_id медіафайлів цієї сторінки ---
    media_file_ids = []
    for msg in page_msgs:
        _, fid = _build_message_card(msg, entity_type, current_uid)
        if fid:
            msg_type = msg[5] if len(msg) > 5 else "text"
            media_file_ids.append((fid, msg_type))

    # --- Клавіатура ---
    nav_row = []
    if page_number > 0:
        cb_prev = f"chat_page_{page_number - 1}_{'1' if files_only else '0'}"
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=cb_prev))
    nav_row.append(InlineKeyboardButton(f"📄 {page_number + 1}/{total_pages}", callback_data="ignore"))
    if page_number < total_pages - 1:
        cb_next = f"chat_page_{page_number + 1}_{'1' if files_only else '0'}"
        nav_row.append(InlineKeyboardButton("➡️", callback_data=cb_next))

    # Кнопка фільтра
    if files_only:
        filter_btn = InlineKeyboardButton("📋 Всі повідомлення", callback_data=f"chat_page_0_0")
    else:
        filter_btn = InlineKeyboardButton("📂 Тільки файли/ДЗ", callback_data=f"chat_page_0_1")

    keyboard = [
        nav_row,
        [filter_btn],
        [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_chat_menu")],
    ]

    # Оновлюємо текстове повідомлення
    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception:
        # Повідомлення може бути незмінним (однаковий текст) — ігноруємо
        pass

    # --- Відправляємо медіафайли цієї сторінки окремими повідомленнями ---
    if media_file_ids:
        await bot.send_message(
            chat_id=query.message.chat_id,
            text=f"📎 <i>Медіафайли з цієї сторінки ({len(media_file_ids)} шт.):</i>",
            parse_mode="HTML"
        )
        for fid, ftype in media_file_ids:
            try:
                if ftype == "photo":
                    await bot.send_photo(chat_id=query.message.chat_id, photo=fid)
                elif ftype == "document":
                    await bot.send_document(chat_id=query.message.chat_id, document=fid)
                elif ftype == "audio":
                    await bot.send_audio(chat_id=query.message.chat_id, audio=fid)
                elif ftype == "video":
                    await bot.send_video(chat_id=query.message.chat_id, video=fid)
                elif ftype == "voice":
                    await bot.send_voice(chat_id=query.message.chat_id, voice=fid)
                else:
                    await bot.send_document(chat_id=query.message.chat_id, document=fid)
            except Exception as e:
                print(f"[show_chat_page] Не вдалося відправити медіа {fid}: {e}")


async def common_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user = db.get_user(user_id)

    if data == "ignore":
        return

    elif data == "back_to_menu":
        role = user[4] if user else 'student'
        await query.edit_message_text("Головне меню:")
        await context.bot.send_message(chat_id=user_id, text="Оберіть дію:", reply_markup=get_main_keyboard(role))
        return

    elif data.startswith("cal_"):
        if data.startswith("cal_prev_") or data.startswith("cal_next_"):
            year, month = map(int, data.split("_")[2:4])
            calendar_keyboard = get_calendar_keyboard(year, month)
            await query.edit_message_reply_markup(reply_markup=calendar_keyboard)
        elif data == "cal_today":
            now = datetime.now()
            calendar_keyboard = get_calendar_keyboard(now.year, now.month)
            await query.edit_message_reply_markup(reply_markup=calendar_keyboard)

        elif data.startswith("cal_date_"):
            year, month, day = map(int, data.split("_")[2:5])
            selected_date = datetime(year, month, day).date()

            if user and user[4] == 'teacher':
                lessons = db.get_teacher_lessons(user_id, selected_date)
                text = f"📅 Розклад на {selected_date.strftime('%d.%m.%Y')}\n\n"
                if not lessons:
                    text += "❌ Уроків немає"
                else:
                    for l in lessons:
                        text += f"📚 {format_lesson_time(l[5])} — {'інд.' if l[2] else 'група'}\n"
            else:
                lessons = db.get_student_lessons(user_id, selected_date)
                text = f"📅 Календар на {selected_date.strftime('%d.%m.%Y')}\n\n"
                if not lessons:
                    text += "❌ Уроків немає"
                else:
                    for l in lessons:
                        text += f"📚 {format_lesson_time(l[5])} — {l[9]} {l[10]}\n"

            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_calendar_{year}_{month}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("back_to_calendar_"):
        year, month = map(int, data.split("_")[3:5])
        await query.edit_message_text("📅 Оберіть дату:", reply_markup=get_calendar_keyboard(year, month))


async def route_manager_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_manager_contact_button(update, context)
