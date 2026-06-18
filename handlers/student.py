from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_calendar_keyboard, get_chat_active_keyboard
from utils.helpers import format_lesson_time
from config.settings import STUDENT_CHAT_ACTIVE, STUDENT_MESSAGE_SELECT


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

    # 1. СЬОГОДНІ
    if data == "student_schedule_today":
        today = datetime.now().date()
        lessons = db.get_student_lessons(user_id, today)
        if not lessons:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n❌ Уроків немає"
        else:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n"
            for lesson in lessons:
                lesson_time = format_lesson_time(lesson[5])
                t_first = lesson[9] if (len(lesson) > 9 and lesson[9]) else ""
                t_last = lesson[10] if (len(lesson) > 10 and lesson[10]) else ""
                teacher_full_name = f"{t_first} {t_last}".strip() or "Невідомо"
                
                if lesson[2]: lesson_type = "індивідуально"
                else:
                    g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                    lesson_type = f"група {g_name}"

                text += f"📚 Час: {lesson_time}\n"
                text += f"    👨‍🏫 Викладач: {teacher_full_name}\n"
                text += f"    📋 Тип: {lesson_type}\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 2. НА ТИЖДЕНЬ
    elif data == "student_schedule_week":
        lessons = db.get_student_lessons(user_id)
        if not lessons:
            text = "📅 Мій календар на тиждень\n\n❌ Уроків немає"
        else:
            text = "📅 Мій календар на тиждень\n\n"
            current_date = None
            for lesson in lessons[:14]:
                lesson_date = lesson[4]
                if lesson_date != current_date:
                    current_date = lesson_date
                    try:
                        date_obj = datetime.strptime(lesson_date, '%Y-%m-%d').date()
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        weekday_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
                        weekday = weekday_names[date_obj.weekday()]
                        text += f"\n📅 {formatted_date} ({weekday})\n"
                    except: text += f"\n📅 {lesson_date}\n"

                lesson_time = format_lesson_time(lesson[5])
                t_first = lesson[9] if (len(lesson) > 9 and lesson[9]) else ""
                t_last = lesson[10] if (len(lesson) > 10 and lesson[10]) else ""
                teacher_full_name = f"{t_first} {t_last}".strip() or "Викладач"

                if lesson[2]: lesson_type = "індивідуально"
                else:
                    g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                    lesson_type = f"група {g_name}"

                text += f"  📚 Час: {lesson_time}\n"
                text += f"      👨‍🏫 Викладач: {teacher_full_name}\n"
                text += f"      📋 Тип: {lesson_type}\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 3. ВІДКРИТТЯ СІТКИ КАЛЕНДАРЯ
    elif data == "student_schedule_calendar":
        now = datetime.now()
        # Використовуємо функцію з common.py, яка генерує кнопки з префіксом cal_
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду календаря:",
            reply_markup=get_calendar_keyboard(now.year, now.month)
        )
        return

    # 4. ОБРОБКА КЛІКУ ПО ДАТІ (cal_date_YYYY_MM_DD)
    elif data.startswith("cal_date_"):
        try:
            parts = data.split("_")
            year, month, day = map(int, parts[2:5])
            selected_date = datetime(year, month, day).date()
            
            lessons = db.get_student_lessons(user_id, selected_date)
            
            text = f"📅 Календар на {selected_date.strftime('%d.%m.%Y')}\n\n"
            if not lessons:
                text += "❌ Уроків на цей день не знайдено."
            else:
                for lesson in lessons:
                    lesson_time = format_lesson_time(lesson[5])
                    t_first = lesson[9] if (len(lesson) > 9 and lesson[9]) else ""
                    t_last = lesson[10] if (len(lesson) > 10 and lesson[10]) else ""
                    teacher_name = f"{t_first} {t_last}".strip() or "Невідомо"
                    
                    if lesson[2]: l_type = "індивідуально"
                    else:
                        g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                        l_type = f"група {g_name}"
                        
                    text += f"📚 Час: {lesson_time}\n"
                    text += f"    👨‍🏫 Викладач: {teacher_name}\n"
                    text += f"    📋 Тип: {l_type}\n\n"
            
            # Кнопка повернення до сітки календаря
            keyboard = [[InlineKeyboardButton("⬅️ Назад до календаря", callback_data=f"back_to_calendar_{year}_{month}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            print(f"Error in cal_date: {e}")
        return

    # 5. ГОРТАННЯ МІСЯЦІВ
    elif data.startswith("cal_prev_") or data.startswith("cal_next_") or data == "cal_today":
        if data == "cal_today":
            now = datetime.now()
            y, m = now.year, now.month
        else:
            parts = data.split("_")
            y, m = int(parts[2]), int(parts[3])
        
        await query.edit_message_reply_markup(reply_markup=get_calendar_keyboard(y, m))
        return

    # 6. КНОПКИ ПОВЕРНЕННЯ
    elif data.startswith("back_to_calendar_"):
        parts = data.split("_")
        year, month = int(parts[3]), int(parts[4])
        await query.edit_message_text("📅 Оберіть дату:", reply_markup=get_calendar_keyboard(year, month))
        return

    elif data == "back_student_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="student_schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text("🗓 Мій календар\n\nОберіть формат:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

# --- ТЕКСТОВІ КНОПКИ УЧНЯ (handle_message) ---

async def menu_about_school(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏫 <b>Про нашу школу UKnow</b>\n\n"
        "🇺🇦 Ми українська онлайн школа UKnow. Працюємо з 2022 року і допомагаємо українцям в різних куточках світу оволодіти мовою і інтегруватися в суспільство.\n\n"
        "🌎 Сьогодні ми пропонуємо уроки з англійської, іспанської, польської, французької, італійської, чеської, словацької, німецької та турецької мов\n\n"
        "🎉 Ми вже випустили більше 4000 студентів\n\n"
        "👨‍🏫 Наші викладачі проходять 4 етапи відбору, перед тим як приступити до занять.\n\n"
        "🎯 Ми можемо підготувати Вас до екзаменів на знання мови, до екзамену на вступ у ВНЗ, допомогти Вам заговорити за 36 уроків, або отримати найвищу оцінку при оформлені документів.",
        parse_mode='HTML'
    )


async def menu_school_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 <b>Правила школи</b> 🚨\n\n"
        "З повним переліком правил роботи школи ви можете ознайомитися у договорі який вам надав ваш менеджер ✅\n\n"
        "Для вашої зручності додаємо сюди основні моменти:\n\n"
        "📌 Оплата абонементу є згодою з умовами договору оферти\n"
        "📌 Школа залишає за собою право зміни викладача під час навчального процесу\n"
        "📌 Матеріали та наповнення уроку надається школою та викладачем на свій розсуд\n"
        "📌 Відміна уроку зі сторони вчителя можлива не менше ніж за 2 години до початку\n"
        "📌 Відміна уроку зі сторони учня можлива не менше ніж за 2 години до початку, у разі, якщо попередження про відміну/перенос уроку відбулося менше ніж за 2 години – урок фіксується проведеним\n"
        "📌 У разі запізнення учня на урок на 15 і більше хвилин – урок вважається проведеним\n"
        "📌 Учень має право звертатися у будь який час до представників школи для вирішення навчальних питань та консультації\n"
        "📌 Учень має право «заморозити» навчання, до трьох місяців – попередньо попередивши про це менеджера і погодивши період паузи\n"
        "📌 У разі недоукомплектування групи – школа залишає за собою право закрити групу і запропонувати учневі альтернативні варіанти навчання\n"
        "📌 У разі бажання учня розірвати договір в односторонньому порядку, через недомовленість між школою і учнем у вирішенні організаційних питань – можливе повернення у розмірі 50% від залишку коштів на момент розривання договору. Протягом 14 банківських днів\n"
        "📌 У випадку відсутності одного з учнів на парному/груповому уроці – урок вважається проведеним і надається запис уроку\n"
        "📌 Школа не несе відповідальності, якщо учень не зміг скористатися наданими послугами з причини, які не залежать від школи\n"
        "📌 Абонемент має термін дії, відповідно до кількості занять, після закінчення терміну дії абонементу – невикористані уроки списуються з балансу\n"
        "📌 Підбір пари для міні-групи займає 10-14 робочих днів\n"
        "📌 Умови бронювання навчання (термін бронювання, що викладач та графік може бути зміненим, передоплата не повертається, якщо учень передумав)",
        parse_mode='HTML'
    )


async def menu_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Популярні питання</b>\n\n"
        "- <b>Чи зможу я змінювати графік?</b>\n"
        "Так, Ви можете змінювати графік протягом навчання, попередньо обговоривши це з адміністратором.🗓\n\n"
        "- <b>Чи можна перенести або відмінити урок?</b>\n"
        "Так, Ви можете перенести урок, попередивши нас мінімум за 2️⃣ години до початку.\n\n"
        "- <b>Що робити якщо викладач не прийшов на урок?</b>\n"
        "Напишіть одразу адміністратору.☎️\n\n"
        "- <b>Я отримаю сертифікат про навчання?</b>\n"
        "Обов'язково! Навіть, двома мовами🏅\n\n"
        "- <b>Куди підключатись на урок?</b>\n"
        "В чаті закріплене стале посилання на зустріч👩🏻‍💻\n\n"
        "- <b>Я можу змінити викладача?</b>\n"
        "Так, Вам треба написати своє бажання адміністратору і ми запропонуємо для Вас нового викладача.👩🏻‍🏫\n\n"
        "- <b>Чи є розмовні клуби?</b>\n"
        "Так, з кожної мови.\n\n"
        "- <b>Можна поставити навчання на паузу?</b>\n"
        "Так, ми можемо заморозити навчання на термін до 3х місяців.⏸️\n\n"
        "- <b>Куди відправляти домашнє завдання?</b>\n"
        "Домашнє завдання надсилайте в цей чат бот викладачеві через кнопку «💬 Чат» 📝\n\n"
        "- <b>Як продовжити навчання?</b>\n"
        "За декілька уроків до кінця навчання, Вам напише адміністратор і обговорить продовження. Або ж Ви можете написати самостійно і адміністратор надішле Вам всю інформацію стосовно продовження навчання.📚",
        parse_mode='HTML'
    )

async def menu_student_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
        [InlineKeyboardButton("📅 На тиждень", callback_data="student_schedule_week")],
        [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("🗓 Мій календар\n\nОберіть формат перегляду:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))