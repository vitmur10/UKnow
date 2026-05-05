import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_calendar_keyboard, get_chat_active_keyboard
from utils.helpers import format_lesson_time
from config.settings import TEACHER_CHAT_ACTIVE, TEACHER_MESSAGE_SELECT, KYIV_TZ, now_kyiv


async def teacher_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    existing_user = db.get_user(user_id)
    if existing_user:
        conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'teacher' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    else:
        user = update.effective_user
        db.add_user(user_id, user.username, user.first_name or "", user.last_name or "", 'teacher')

    await update.message.reply_text(
        "👨‍🏫 Ви зареєстровані як викладач!",
        reply_markup=get_main_keyboard('teacher')
    )


async def list_teacher_students(update, context):
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    students = db.get_teacher_students(teacher_id)

    if not students:
        await query.edit_message_text("На жаль, у вас ще немає учнів.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for student in students:
        # Беремо дані за індексами: 0 - ID, 2 - Ім'я, 3 - Прізвище
        student_id = student[0]
        first_name = student[2]
        last_name = student[3]

        # Перевіряємо, щоб не було None, якщо прізвище не вказано
        full_name = f"{first_name} {last_name}" if last_name else first_name

        keyboard.append([InlineKeyboardButton(full_name, callback_data=f"view_chat_teacher_student_{student_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть учня, щоб переглянути історію чату:**", reply_markup=reply_markup,
                                  parse_mode='HTML')


async def show_students(update, context):
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    students = db.get_teacher_students(teacher_id)

    if not students:
        await query.edit_message_text("На жаль, у вас ще немає учнів.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for student in students:
        student_id, first_name, last_name = student
        keyboard.append([InlineKeyboardButton(f"{first_name} {last_name}",
                                              callback_data=f"view_chat_teacher_student_{student_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть учня, щоб переглянути історію чату:**", reply_markup=reply_markup,
                                  parse_mode='HTML')


async def show_groups(update, context):
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    groups = db.get_teacher_groups(teacher_id)

    if not groups:
        await query.edit_message_text("Ви не прив'язані до жодної групи.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for group_id, group_name in groups:
        keyboard.append([InlineKeyboardButton(group_name, callback_data=f"view_chat_teacher_group_{group_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть групу, щоб переглянути історію чату:**", reply_markup=reply_markup,
                                  parse_mode='HTML')


async def teacher_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує викладачу список учнів з непрочитаними повідомленнями."""
    teacher_id = update.effective_user.id
    unread_list = db.get_unread_count_per_student(teacher_id)

    if not unread_list:
        await update.message.reply_text(
            "📭 Нових повідомлень немає.\n\n"
            "Всі повідомлення прочитані ✅"
        )
        return

    keyboard = []
    for student_id, first_name, last_name, count, last_time, last_msg in unread_list:
        preview = (last_msg or "")[:30].replace("\n", " ")
        if len(last_msg or "") > 30:
            preview += "…"
        label = f"🔴 {first_name} {last_name}  [{count} нових]  {preview}"
        keyboard.append([InlineKeyboardButton(
            label,
            callback_data=f"inbox_open_{student_id}"
        )])

    total = sum(row[3] for row in unread_list)
    await update.message.reply_text(
        f"📬 <b>Вхідні</b> — {total} нових повідомлень\n\n"
        f"Оберіть учня щоб прочитати та відповісти:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def teacher_inbox_open(query, context, student_id: int):
    """Відкриває листування з конкретним учнем і позначає як прочитане."""
    teacher_id = query.from_user.id

    # Позначаємо повідомлення прочитаними
    db.mark_messages_read(from_user_id=student_id, to_user_id=teacher_id)

    # Отримуємо останні 10 повідомлень
    messages = db.get_chat_history(user1_id=teacher_id, user2_id=student_id)
    student = db.get_user(student_id)
    student_name = f"{student[2]} {student[3]}" if student else "Невідомо"

    if not messages:
        text = f"👨‍🎓 <b>{student_name}</b>\n\n❌ Повідомлень ще немає."
    else:
        text = f"👨‍🎓 <b>{student_name}</b> — останні повідомлення:\n\n"
        # Показуємо останні 8 повідомлень (messages сортовані DESC)
        for msg in reversed(messages[:8]):
            try:
                dt = datetime.fromisoformat(msg[6]) + timedelta(hours=2)
                ts = dt.strftime("%d.%m %H:%M")
                msg_text = (msg[4] or "").strip() or "— (медіа)"
                if len(msg_text) > 200:
                    msg_text = msg_text[:197] + "…"
                sender = "Ви" if msg[1] == teacher_id else student_name.split()[0]
                text += f"<b>{sender}</b> <i>{ts}</i>\n{msg_text}\n\n"
            except Exception as e:
                print(f"Inbox render error: {e}")
                continue

    keyboard = [
        [InlineKeyboardButton(
            f"↩️ Відповісти {student_name.split()[0]}",
            callback_data=f"inbox_reply_{student_id}"
        )],
        [InlineKeyboardButton("⬅️ До вхідніх", callback_data="inbox_back")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def show_teacher_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user or user[4] != 'teacher':
        await update.message.reply_text("Ця функція доступна лише викладачам.")
        return

    groups = db.get_teacher_groups(user_id)
    if not groups:
        await update.message.reply_text("У вас ще немає груп.")
        return

    text = "👥 Мої групи:\n\n"
    for group in groups:
        members = db.get_group_members(group[0])
        text += f"📚 {group[1]} ({group[3]})\n"
        text += f"👥 Учасників: {len(members)}\n"
        if members:
            text += "Учні: "
            text += ", ".join([f"{member[2]} {member[3]}" for member in members[:3]])
            if len(members) > 3:
                text += f" і ще {len(members) - 3}"
        text += "\n\n"

    await update.message.reply_text(text)


async def show_teacher_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE, teacher_id):
    """
    Показує викладачеві список чатів (учні та групи) для перегляду історії.
    """
    # Отримуємо дані
    assigned_students = db.get_teacher_students(teacher_id)
    assigned_groups = db.get_teacher_groups(teacher_id)

    # Логування для перевірки в терміналі
    print(f"DEBUG: Students found: {len(assigned_students) if assigned_students else 0}")
    print(f"DEBUG: Groups found: {len(assigned_groups) if assigned_groups else 0}")

    keyboard = []

    # Додаємо кнопки для учнів
    if assigned_students:
        for student in assigned_students:
            s_id = student[0]
            first_name = student[2] if student[2] else "Учень"
            last_name = student[3] if student[3] else ""

            # РЕКОМЕНДАЦІЯ: Перевірте, чи chat_engine очікує саме такий callback_data!
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 {first_name} {last_name}",
                callback_data=f"view_chat_teacher_student_{s_id}"
            )])

    # Додаємо кнопки для груп
    if assigned_groups:
        for group in assigned_groups:
            g_id = group[0]
            g_name = group[1]
            keyboard.append([InlineKeyboardButton(
                f"👥 Група: {g_name}",
                callback_data=f"view_chat_teacher_group_{g_id}"
            )])

    if not assigned_students and not assigned_groups:
        text = "У вас ще немає призначених чатів для перегляду."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📖 **Історія переписок**\n\nОберіть чат для перегляду:"

    # Обробка як повідомлення, так і колбеку
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


# --- ІНЛАЙН КНОПКИ ВИКЛАДАЧА ---
async def teacher_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    # --- 📬 ВХІДНІ (INBOX) ---
    if data.startswith("inbox_open_"):
        student_id = int(data.split("_")[2])
        await teacher_inbox_open(query, context, student_id)
        return
    elif data == "inbox_back":
        # Повернення до списку вхідніх
        teacher_id = query.from_user.id
        unread_list = db.get_unread_count_per_student(teacher_id)
        if not unread_list:
            await query.edit_message_text("📭 Нових повідомлень немає.")
            return
        keyboard = []
        for sid, fn, ln, count, last_time, last_msg in unread_list:
            preview = (last_msg or "")[:30].replace("\n", " ")
            if len(last_msg or "") > 30:
                preview += "…"
            keyboard.append([InlineKeyboardButton(
                f"🔴 {fn} {ln}  [{count} нових]  {preview}",
                callback_data=f"inbox_open_{sid}"
            )])
        total = sum(r[3] for r in unread_list)
        await query.edit_message_text(
            f"📬 <b>Вхідні</b> — {total} нових повідомлень\n\nОберіть учня:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return
    elif data == "schedule_today":
        today = now_kyiv().date()
        lessons = db.get_teacher_lessons(user_id, today)

        if not lessons:
            text = f"📅 Розклад на сьогодні ({today.strftime('%d.%m.%Y')})\n\n❌ Уроків немає"
        else:
            text = f"📅 Розклад на сьогодні ({today.strftime('%d.%m.%Y')})\n\n"
            for lesson in lessons:
                lesson_time = format_lesson_time(lesson[5])
                if lesson[2]:  # individual lesson
                    student_name = f"{lesson[9]} {lesson[10]}" if lesson[9] and lesson[
                        10] else "Невідомо"
                    text += f"📚 Час: {lesson_time}\n"
                    text += f"    👨‍🎓 Учень: {student_name} (індивідуально)\n\n"
                else:  # group lesson
                    group_name = lesson[11] if lesson[11] else "Невідомо"
                    text += f"📚 Час: {lesson_time}\n"
                    text += f"    👥 Група: {group_name}\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "schedule_week":
        lessons = db.get_teacher_lessons(user_id)

        if not lessons:
            text = "📆 Розклад на тиждень\n\n❌ Уроків немає"
        else:
            text = "📆 Розклад на тиждень\n\n"
            current_date = None
            for lesson in lessons[:14]:
                lesson_date = lesson[4]

                if lesson_date != current_date:
                    current_date = lesson_date
                    try:
                        date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        weekday_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
                        weekday = weekday_names[date_obj.weekday()]
                        text += f"\n📅 {formatted_date} ({weekday})\n"
                    except:
                        text += f"\n📅 {current_date}\n"

                lesson_time = format_lesson_time(lesson[5])

                # --- ОНОВЛЕНА ЛОГІКА ВИВОДУ (УЧЕНЬ АБО ГРУПА) ---
                if lesson[2]:  # Індивідуальний учень
                    first_name = lesson[9] if (len(lesson) > 9 and lesson[9]) else ""
                    last_name = lesson[10] if (len(lesson) > 10 and lesson[10]) else ""
                    full_name = f"{first_name} {last_name}".strip()
                    student_name = full_name if full_name else "Учень"

                    text += f"  📚 Час: {lesson_time}\n"
                    text += f"      👨‍🎓 Учень: {student_name} (індивідуально)\n"

                elif lesson[3]:  # Груповий урок
                    g_id = lesson[3]
                    # Намагаємось дістати назву групи з бази за її ID
                    group_info = db.get_group(g_id)
                    if group_info:
                        g_name = group_info[1]  # Індекс 1 — це зазвичай назва групи
                    else:
                        # Якщо в базі не знайшли, пробуємо взяти з результату запиту
                        g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Група"

                    text += f"  📚 Час: {lesson_time}\n"
                    text += f"      👥 Група: {g_name}\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    elif data == "schedule_calendar":
        now = now_kyiv()
        calendar_keyboard = get_calendar_keyboard(now.year, now.month)
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду розкладу:",
            reply_markup=calendar_keyboard
        )
        return
    elif data == "back_schedule" or data == "back_to_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "📆 Мій розклад\n\nОберіть період для перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


# --- ТЕКСТОВІ КНОПКИ ВИКЛАДАЧА ---
async def menu_teacher_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Сьогодні", callback_data="schedule_today")],
        [InlineKeyboardButton("📆 На тиждень", callback_data="schedule_week")],
        [InlineKeyboardButton("🗓 Календар", callback_data="schedule_calendar")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("📆 Мій розклад\n\nОберіть період для перегляду:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_teacher_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    students = db.get_teacher_students(user_id)
    if not students:
        await update.message.reply_text("У вас ще немає учнів.")
    else:
        text = "👨‍🎓 Мої учні:\n\n"
        for student in students:
            # Добавляем только эту проверку. Если данных нет — пропускаем итерацию.
            if not student:
                continue

            # Используем .get или проверку на None для каждой строки, чтобы не вылетало
            first_name = student[2] if student[2] else "Учень"
            last_name = student[3] if student[3] else ""
            # Проверка индекса 6, чтобы бот не упал, если данных меньше
            language = student[6] if len(student) > 6 and student[6] else "Не вказано"

            text += f"👨‍🎓 {first_name} {last_name}\n"
            text += f"🗣 {language}\n\n"

        await update.message.reply_text(text)
    return


async def menu_teacher_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if user and user[4] == 'teacher':
        students_count = len(db.get_teacher_students(user_id))
        groups_count = len(db.get_teacher_groups(user_id))
        lessons_count = len(db.get_teacher_lessons(user_id))
        await update.message.reply_text(
            f"📊 Ваша статистика:\n\n"
            f"👥 Учнів: {students_count}\n"
            f"👥 Груп: {groups_count}\n"
            f"📚 Заплановано уроків: {lessons_count}"
        )