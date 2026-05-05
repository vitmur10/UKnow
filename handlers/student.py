from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_calendar_keyboard, get_chat_active_keyboard
from utils.helpers import format_lesson_time
from config.settings import STUDENT_CHAT_ACTIVE, STUDENT_MESSAGE_SELECT, KYIV_TZ, now_kyiv


async def show_student_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE, student_id):
    # Отримуємо викладача та групи учня
    teacher = db.get_student_teacher(student_id)
    student_groups = db.get_student_groups(student_id)

    keyboard = []

    # Виправлений блок
    if teacher:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🏫 Чат з викладачем {teacher[2]} {teacher[3]}",
            callback_data=f"view_chat_student_teacher_{teacher[0]}"
        )])

    if student_groups:
        # Додаємо кнопки для групових чатів
        for group in student_groups:
            keyboard.append([InlineKeyboardButton(
                f"👥 Чат групи '{group[1]}'",
                callback_data=f"view_chat_student_group_{group[0]}"
            )])

    if not teacher and not student_groups:
        await update.message.reply_text("У вас ще немає призначених чатів для перегляду.")
        return

    keyboard.append([InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_to_menu")])

    await update.message.reply_text(
        "📖 Історія переписок\n\nОберіть чат для перегляду:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def student_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "student_schedule_today":
        today = now_kyiv().date()
        lessons = db.get_student_lessons(user_id, today)

        if not lessons:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n❌ Уроків немає"
        else:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n"
            for lesson in lessons:
                lesson_time = format_lesson_time(lesson[5])  # lesson_time это индекс 5
                teacher_name = f"{lesson[9]} {lesson[10]}" if lesson[9] and lesson[10] else "Невідомо"  # индексы 9,10

                # Определяем тип урока
                if lesson[2]:  # индивидуальный урок
                    lesson_type = "індивідуально"
                else:  # групповой урок
                    group_name = lesson[11] if lesson[11] else "Невідомо"  # group_name это индекс 11
                    lesson_type = f"група {group_name}"

                text += f"📚 Час: {lesson_time}\n"
                text += f"    👨‍🏫 Викладач: {teacher_name}\n"
                text += f"    📋 Тип: {lesson_type}\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "student_schedule_week":
        lessons = db.get_student_lessons(user_id)

        if not lessons:
            text = "📅 Мій календар на тиждень\n\n❌ Уроків немає"
        else:
            text = "📅 Мій календар на тиждень\n\n"
            current_date = None
            for lesson in lessons[:14]:  # Обмежуємо до 14 уроків
                lesson_date = lesson[4]

                if lesson_date != current_date:
                    current_date = lesson_date
                    try:
                        date_obj = datetime.strptime(lesson_date, '%Y-%m-%d').date()
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        weekday_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота',
                                         'Неділя']
                        weekday = weekday_names[date_obj.weekday()]
                        text += f"\n📅 {formatted_date} ({weekday})\n"
                    except (ValueError, TypeError):
                        text += f"\n📅 {lesson_date}\n"

                # --- ВИПРАВЛЕНО: Чистимо ім'я викладача від None ---
                lesson_time = format_lesson_time(lesson[5])
                t_first = lesson[9] if lesson[9] else ""
                t_last = lesson[10] if lesson[10] else ""
                teacher_name = f"{t_first} {t_last}".strip() or "Викладач"

                # Визначаємо тип уроку
                if lesson[2]:  # індивідуально
                    lesson_type = "індивідуально"
                else:  # група
                    g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                    lesson_type = f"група {g_name}"

                text += f"  📚 Час: {lesson_time}\n"
                text += f"      👨‍🏫 Викладач: {teacher_name}\n"
                text += f"      📋 Тип: {lesson_type}\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    # Календар студента
    elif data == "student_schedule_calendar":
        now = now_kyiv()
        calendar_keyboard = get_calendar_keyboard(now.year, now.month)
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду календаря:",
            reply_markup=calendar_keyboard
        )
        return
    elif data == "back_student_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="student_schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "🗓 Мій календар\n\nОберіть формат перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


# --- ТЕКСТОВІ КНОПКИ УЧНЯ (handle_message) ---
async def menu_about_school(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏫 Про нашу школу UKnow\n\n🇺🇦 Ми українська онлайн школа...")


async def menu_school_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Правила школи 🚨\n\nЗ повним переліком правил...")


async def menu_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Популярні питання\n\n- Чи зможу я змінювати графік?...")


async def menu_student_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
        [InlineKeyboardButton("📅 На тиждень", callback_data="student_schedule_week")],
        [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("🗓 Мій календар\n\nОберіть формат перегляду:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))