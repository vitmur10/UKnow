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
        await query.edit_message_text("На жаль, у вас ще немає учнів.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for student in students:
        student_id, first_name, last_name = student
        keyboard.append([InlineKeyboardButton(f"{first_name} {last_name}", callback_data=f"chat_{student_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть учня, щоб переглянути історію чату:**", reply_markup=reply_markup, parse_mode='HTML')


async def show_students(update, context):
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    students = db.get_teacher_students(teacher_id)

    if not students:
        await query.edit_message_text("На жаль, у вас ще немає учнів.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for student in students:
        student_id, first_name, last_name = student
        keyboard.append([InlineKeyboardButton(f"{first_name} {last_name}", callback_data=f"chat_{student_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть учня, щоб переглянути історію чату:**", reply_markup=reply_markup, parse_mode='HTML')


async def show_groups(update, context):
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    groups = db.get_teacher_groups(teacher_id)

    if not groups:
        await query.edit_message_text("Ви не прив'язані до жодної групи.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")]]))
        return

    keyboard = []
    for group_id, group_name in groups:
        keyboard.append([InlineKeyboardButton(group_name, callback_data=f"group_chat_{group_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_teacher_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 **Оберіть групу, щоб переглянути історію чату:**", reply_markup=reply_markup, parse_mode='HTML')


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
        # Обрізаємо попередній перегляд до 30 символів
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
    # Отримуємо учнів, призначених викладачеві
    assigned_students = db.get_teacher_students(teacher_id)
    # Отримуємо групи, призначені викладачеві
    assigned_groups = db.get_teacher_groups(teacher_id)
    print(f"DEBUG: Students found: {assigned_students}")
    print(f"DEBUG: Groups found: {assigned_groups}")

    keyboard = []

    # Додаємо кнопки для чатів з учнями
    if assigned_students:
        for student in assigned_students:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 Чат з учнем {student[2]} {student[3]}",
                callback_data=f"view_chat_teacher_student_{student[0]}"
            )])

    # Додаємо кнопки для групових чатів
    if assigned_groups:
        for group in assigned_groups:
            keyboard.append([InlineKeyboardButton(
                f"👥 Чат групи '{group[1]}'",
                callback_data=f"view_chat_teacher_group_{group[0]}"
            )])

    if not assigned_students and not assigned_groups:
        await update.message.reply_text("У вас ще немає призначених чатів для перегляду.")
        return

    keyboard.append([InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_to_menu")])

    await update.message.reply_text(
        "📖 Історія переписок\n\nОберіть чат для перегляду:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
