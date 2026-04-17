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

# TODO: Перенести обробники текстових кнопок ("Мій календар", "Про школу") з handle_message сюди.