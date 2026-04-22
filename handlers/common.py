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


async def show_chat_page(query, context, page_number):
    messages = context.user_data.get('current_chat_messages', [])
    title = context.user_data.get('current_chat_title', '')
    entity_type = context.user_data.get('current_chat_entity_type', '')

    total_messages = len(messages)
    MESSAGES_PER_PAGE = 10
    total_pages = (total_messages + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE

    start_index = page_number * MESSAGES_PER_PAGE
    end_index = start_index + MESSAGES_PER_PAGE

    page_messages = messages[start_index:end_index]

    if not page_messages:
        text = f"{title}\n\n❌ Повідомлень немає на цій сторінці"
    else:
        if entity_type == "teacher":
            teacher_name = title.replace("👨‍🏫 Історія чатів викладача ", "")
            text = f"<b>{teacher_name}</b>\n\n(Сторінка {page_number + 1} з {total_pages})\n\n"
        else:
            text = f"{title}\n\n(Сторінка {page_number + 1} з {total_pages})\n\n"

        for msg in page_messages:
            try:
                if len(msg) > 4 and isinstance(msg[4], str) and msg[4].strip():
                    message_text = msg[4]
                elif len(msg) > 3 and isinstance(msg[3], str) and msg[3].strip():
                    message_text = msg[3]
                else:
                    message_text = ""

                # ОБМЕЖЕННЯ: Якщо одне повідомлення занадто довге, обрізаємо його
                if len(message_text) > 300:
                    message_text = message_text[:297] + "..."

                dt_obj = datetime.fromisoformat(msg[6])
                dt_corrected = dt_obj + timedelta(hours=2)
                timestamp = dt_corrected.strftime("📅 %d.%m ⏰ %H:%M")

                sender_first = msg[7] if len(msg) > 7 and msg[7] else ""
                sender_role = msg[8] if len(msg) > 8 and msg[8] else ""
                sender_name = f"{sender_first} {sender_role}".strip() if sender_first or sender_role else "Невідомо"

                new_line = ""
                if entity_type == "teacher":
                    student_id = msg[2]
                    student_user = db.get_user(student_id)
                    student_name = f"{student_user[2]} {student_user[3]}" if student_user else "Невідомо"
                    new_line = f"<b>Кому: {student_name}</b> {timestamp} {sender_name}: {message_text}\n"
                else:
                    new_line = f"{timestamp} {sender_name}: {message_text}\n"

                # ПЕРЕВІРКА: чи влізе новий рядок у ліміт 4096 символів
                if len(text) + len(new_line) > 4000:
                    text += "\n⚠️ <i>Частина повідомлень не влізла на сторінку...</i>"
                    break

                text += new_line

            except Exception as e:
                print(f"Error processing message: {msg}, error: {e}")
                continue

    # Кнопки пагінації
    keyboard_row = []
    if page_number > 0:
        keyboard_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_page_{page_number - 1}"))
    if page_number < total_pages - 1:
        keyboard_row.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"chat_page_{page_number + 1}"))

    keyboard = [
        keyboard_row,
        [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_chat_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


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
