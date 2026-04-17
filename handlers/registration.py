async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Повністю очищуємо тимчасову пам'ять
    context.user_data.clear()

    # Скидаємо прапорці пошуку, щоб не було помилок з ID
    context.user_data['waiting_for_search_name'] = False
    context.user_data['waiting_for_date'] = False

    user = update.effective_user
    existing_user = db.get_user(user.id)

    if existing_user:
        role = existing_user[4]

        # Відправляємо головне меню
        await update.message.reply_text(
            f"З поверненням, {user.first_name}! 👋\nЩо будемо робити сьогодні?",
            reply_markup=get_main_keyboard(role)
        )

        await send_manager_contact_button(update, context)

        # ПРИМУСОВО завершуємо розмову для ConversationHandler
        return ConversationHandler.END

    # Якщо юзера немає в базі — починаємо реєстрацію
    await update.message.reply_text(
        "Вітаємо в нашій мовній школі UKnow! 🎓🇺🇦\n\n"
        "Давайте почнемо реєстрацію.\n\n"
        "Будь ласка, введіть ваше Прізвище та Ім'я (спочатку Прізвище, потім Ім'я):"
    )
    return REGISTER_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text.strip()
    name_parts = full_name.split()

    if len(name_parts) < 2:
        await update.message.reply_text("Будь ласка, введіть Прізвище та Ім'я (мінімум два слова):")
        return REGISTER_NAME

    context.user_data['first_name'] = name_parts[0]
    context.user_data['last_name'] = ' '.join(name_parts[1:])

    await update.message.reply_text(
        "Чудово! Тепер оберіть мову, яку ви вивчаєте:",
        reply_markup=get_language_keyboard()
    )
    return REGISTER_LANG


async def register_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        lang_index = int(query.data.split("_")[1])
        language = LANGUAGES[lang_index].split(" ", 1)[1]  # Remove emoji
        context.user_data['language'] = language

        await query.edit_message_text(
            f"Обрана мова: {LANGUAGES[lang_index]}\n\n"
            "Тепер введіть вашу дату народження у форматі ДД.ММ.РРРР:"
        )
        return REGISTER_BIRTHDATE


async def register_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdate = update.message.text.strip()

    try:
        datetime.strptime(birthdate, "%d.%m.%Y")
        context.user_data['birthdate'] = birthdate
    except ValueError:
        await update.message.reply_text("Неправильний формат дати. Введіть у форматі ДД.ММ.РРРР:")
        return REGISTER_BIRTHDATE

    await update.message.reply_text("Введіть ваш номер телефону:")
    return REGISTER_PHONE


async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user = update.effective_user

    db.add_user(user.id, user.username, context.user_data['first_name'],
                context.user_data['last_name'], 'student')
    db.update_user_info(user.id, phone, context.user_data['language'],
                        context.user_data['birthdate'])

    # --- НОВИЙ БЛОК: Автоматична відправка в Google Таблицю ---
    # --- ОНОВЛЕНИЙ БЛОК: Автоматична відправка в Google Таблицю ---
    try:
        # Формуємо рядок чітко під формат нашої таблиці (7 колонок)
        # 1. ID | 2. ПІБ | 3. Телефон | 4. Викладач | 5. Статус | 6. Група | 7. Дата народження
        new_student_row = [
            str(user.id),  # A: ID
            f"{context.user_data['first_name']} {context.user_data['last_name']}".strip(),  # B: ПІБ
            str(phone),  # C: Номер телефону
            "-",  # D: Викладач (ще немає)
            "student",  # E: Статус
            "Новий (очікує групи)",  # F: Група
            str(context.user_data.get('birthdate', '-'))  # G: Дата народження
        ]

        # ВІДПРАВКА ОДНОГО РЯДКА (Наш Script v10 не видалить базу, бо це не масив масивів)
        payload = {"sheetName": "Учні", "values": new_student_row}
        import requests
        requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=10)

    except Exception as e:
        print(f"Помилка авто-синхронізації: {e}")
    # -------------------------------------------------------

    welcome_text = f"""
Вітаємо в мовній школі UKnow👋🏻

✅ Ваша реєстрація успішно завершена
📚 Мова навчання: {context.user_data['language']}
👩‍🏫 Очікуйте на призначення викладача

📩 Усе подальше спілкування з викладачем відбуватиметься в цьому боті.
У день запланованого заняття зранку Ви отримуватимете нагадування, щоб нічого не пропустити 😊

📌 Просимо звернути увагу на кілька організаційних моментів:
• Якщо Вам потрібно перенести або скасувати урок - будь ласка, повідомте нас не пізніше ніж за 2 години до початку.
• Якщо повідомлення надійшло пізніше - заняття зараховується як проведене та списується з абонементу.
• У разі запізнення урок проводиться в межах залишку запланованого часу.

ℹ️ Більше інформації про правила та роботу школи Ви можете знайти в основному меню цього бота, або задати адміністратору.

Незабаром з Вами зв’яжеться адміністрація для подальших кроків ✨
Раді бути частиною Вашого мовного шляху 💙
"""

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard('student')
    )

    # Отправляем кнопку менеджера новому пользователю
    await send_manager_contact_button(update, context)

    return ConversationHandler.END
