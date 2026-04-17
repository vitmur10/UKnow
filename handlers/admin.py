async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Проверить, является ли пользователь главным админом (автоматические права)
    if user_id == SUPER_ADMIN_ID:
        # Убедиться что главный админ есть в базе
        existing_user = db.get_user(user_id)
        if existing_user:
            conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        else:
            user = update.effective_user
            db.add_user(user_id, user.username, user.first_name or "", user.last_name or "", 'admin')

        await update.message.reply_text(
            "👑 Вітаємо, головний адміністратор!\n\n"
            "🔧 Панель управління активована\n\n"
            "Спеціальні команди:\n"
            "• /add_new_admin [ID] - призначити адміністратора\n"
            "• /remove_admin [ID] - прибрати права адміністратора\n"
            "• /admin_list - список всіх адміністраторів",
            reply_markup=get_main_keyboard('admin')
        )
        return

    # Проверить, назначен ли пользователь админом главным админом
    user = db.get_user(user_id)
    if user and user[4] == 'admin':
        await update.message.reply_text(
            "👨‍💼 Вітаємо, адміністратор!\n\n"
            "🔧 Панель управління активована",
            reply_markup=get_main_keyboard('admin')
        )
        return

    # Если у пользователя нет прав админа
    await update.message.reply_text(
        "❌ У вас немає прав адміністратора.\n\n"
        "Тільки головний адміністратор може надавати права доступу."
    )


def init_super_admin():
    """Инициализация главного администратора при запуске бота"""
    existing_user = db.get_user(SUPER_ADMIN_ID)
    if not existing_user:
        # Если главного админа нет в базе, создаем запись
        db.add_user(SUPER_ADMIN_ID, "SuperAdmin", "Головний", "Адміністратор", 'admin')
        print(f"🔧 Головний адміністратор ініціалізований: ID {SUPER_ADMIN_ID}")
    else:
        # Убедиться что у него роль admin
        if existing_user[4] != 'admin':
            conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (SUPER_ADMIN_ID,))
            conn.commit()
            conn.close()
            print(f"🔧 Права адміністратора відновлені для ID {SUPER_ADMIN_ID}")


async def make_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Только главный админ может назначать других админов
    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Тільки головний адміністратор може призначати адміністраторів.")
        return

    # Проверить аргументы команды
    if not context.args:
        await update.message.reply_text(
            "❌ Вкажіть ID користувача.\n"
            "Приклад: /make_admin 123456789"
        )
        return

    try:
        target_user_id = int(context.args[0])

        # Нельзя назначить самого себя (главный админ уже админ)
        if target_user_id == SUPER_ADMIN_ID:
            await update.message.reply_text("❌ Ви вже головний адміністратор.")
            return

        target_user = db.get_user(target_user_id)

        if not target_user:
            await update.message.reply_text("❌ Користувач з таким ID не знайдений в системі.")
            return

        if target_user[4] == 'admin':
            await update.message.reply_text(f"❌ {target_user[2]} {target_user[3]} вже є адміністратором.")
            return

        # Назначить администратором
        conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ {target_user[2]} {target_user[3]} призначено адміністратором!"
        )

        # Уведомить нового админа
        try:
            await context.bot.send_message(
                target_user_id,
                "🎉 Вітаємо! Ви отримали права адміністратора!\n\n"
                "Тепер ви можете керувати системою.",
                reply_markup=get_main_keyboard('admin')
            )
        except:
            await update.message.reply_text("⚠️ Не вдалося повідомити користувача про призначення.")

    except ValueError:
        await update.message.reply_text("❌ Неправильний ID. Введіть число.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Только главный админ может убирать права админа
    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Тільки головний адміністратор може прибирати права адміністратора.")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Вкажіть ID користувача.\n"
            "Приклад: /remove_admin 123456789"
        )
        return

    try:
        target_user_id = int(context.args[0])

        # Нельзя убрать права у главного админа
        if target_user_id == SUPER_ADMIN_ID:
            await update.message.reply_text("❌ Не можна прибрати права у головного адміністратора.")
            return

        target_user = db.get_user(target_user_id)

        if not target_user:
            await update.message.reply_text("❌ Користувач з таким ID не знайдений.")
            return

        if target_user[4] != 'admin':
            await update.message.reply_text(f"❌ {target_user[2]} {target_user[3]} не є адміністратором.")
            return

        # Убрать права админа
        db.remove_admin_rights(target_user_id)

        await update.message.reply_text(
            f"✅ Права адміністратора прибрано у {target_user[2]} {target_user[3]}.\n"
            f"Тепер це звичайний студент."
        )

        # Уведомить бывшего админа
        try:
            await context.bot.send_message(
                target_user_id,
                "📢 Ваші права адміністратора були прибрані головним адміністратором.\n"
                "Тепер ви маєте статус студента.",
                reply_markup=get_main_keyboard('student')
            )
        except:
            await update.message.reply_text("⚠️ Не вдалося повідомити користувача про зміни.")

    except ValueError:
        await update.message.reply_text("❌ Неправильний ID. Введіть число.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def admin_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Только главный админ может смотреть список админов
    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Тільки головний адміністратор має доступ до списку адміністраторів.")
        return

    admins = db.get_admin_list()

    if not admins:
        await update.message.reply_text("📋 В системі немає адміністраторів (окрім вас).")
        return

    text = "👥 Список адміністраторів:\n\n"

    for admin in admins:
        if admin[0] == SUPER_ADMIN_ID:
            text += f"👑 {admin[2]} {admin[3]} (ID: {admin[0]}) - Головний адміністратор\n"
        else:
            text += f"👨‍💼 {admin[2]} {admin[3]} (ID: {admin[0]}) - Адміністратор\n"

    await update.message.reply_text(text)


async def check_database_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Синхронізація УСІХ уроків одним пакетом (швидко та надійно)"""
    user_id = update.effective_user.id

    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Тільки головний адміністратор може перевіряти базу.")
        return

    await update.message.reply_text("🔄 Починаю швидке вивантаження всіх уроків у Google...")

    try:
        import sqlite3
        conn = sqlite3.connect(db.db_name, timeout=30)
        cursor = conn.cursor()

        # Беремо всі заплановані уроки
        cursor.execute('''SELECT l.lesson_date, l.lesson_time,
                                 t.first_name, t.last_name,
                                 s.first_name, s.last_name,
                                 g.name
                          FROM lessons l
                          LEFT JOIN users t ON l.teacher_id = t.user_id
                          LEFT JOIN users s ON l.student_id = s.user_id
                          LEFT JOIN groups g ON l.group_id = g.id
                          WHERE l.status = 'scheduled' 
                          ORDER BY l.lesson_date ASC, l.lesson_time ASC''')

        lessons = cursor.fetchall()
        conn.close()

        if not lessons:
            await update.message.reply_text("📅 Запланованих уроків не знайдено.")
            return

        all_lessons_rows = []  # Сюди збираємо всі дані

        for lesson in lessons:
            # Формуємо рядок (5 колонок)
            row = [
                str(lesson[0]),  # Дата
                str(lesson[1]),  # Час
                f"{lesson[4]} {lesson[5]}" if lesson[4] else "Група",  # Студент
                f"{lesson[2]} {lesson[3]}" if lesson[2] else "Невідомо",  # Викладач
                str(lesson[6]) if lesson[6] else "Індивідуально"  # Назва групи
            ]
            all_lessons_rows.append(row)

        # 🎯 ВІДПРАВЛЯЄМО ВСЕ ОДНИМ ПАКЕТОМ
        # Використовуємо вашу функцію send_to_google, але з параметром is_bulk=True
        success = send_to_google("Уроки", all_lessons_rows, is_bulk=True)

        if success:
            await update.message.reply_text(f"✅ Успішно! Синхронізовано уроків: {len(all_lessons_rows)}")
        else:
            await update.message.reply_text("❌ Google відхилив запит. Перевірте лог у консолі.")

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    print("--- DEBUG: Спрацював НОВИЙ broadcast_start (ConversationHandler)! ---")
    """Запускає розмову розсилки та просить обрати ціль."""

    # ПЕРЕВІРКА: Цей блок коду, ймовірно, знаходиться за межами ConversationHandler
    # і буде викликаний тільки при натисканні на кнопку "Масова розсилка",
    # яка доступна лише адміну. Проте, ви можете залишити перевірку, якщо вона потрібна.
    # if update.effective_user.id != SUPER_ADMIN_ID:
    #     pass

    # 🎯 КЛЮЧОВА ЗМІНА: Надсилаємо клавіатуру вибору цілі
    await update.message.reply_text(
        "📢 **Режим масової розсилки.** Оберіть цільову аудиторію:",
        reply_markup=get_broadcast_target_keyboard(),  # <--- ТУТ ВИКЛИКАЄТЬСЯ ВАША ФУНКЦІЯ
        parse_mode='Markdown'
    )

    # 🎯 КЛЮЧОВА ЗМІНА: Перехід до стану очікування вибору цілі
    return BROADCAST_SELECT_TARGET


async def broadcast_select_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробляє вибір цільової аудиторії."""
    query = update.callback_query
    await query.answer()

    data = query.data  # Отримаємо 'bc_target_students_all' або 'bc_target_teachers_all'

    # 1. Зберігаємо ціль в context.user_data
    context.user_data['broadcast_target'] = data

    # 2. Визначаємо назву цілі для повідомлення
    if data == 'bc_target_students_all':
        target_name = "Учні: ВСІ"
    elif data == 'bc_target_teachers_all':
        target_name = "Викладачі: ВСІ"
    else:
        # Цього не повинно статися
        await query.edit_message_text("Помилка вибору цілі.")
        return ConversationHandler.END

    # Створюємо клавіатуру для скасування
    keyboard = [[InlineKeyboardButton("❌ Скасувати розсилку", callback_data="cancel_broadcast")]]

    await query.edit_message_text(
        f"🎯 **Ціль обрано:** {target_name}.\n\n"
        "Тепер введіть повідомлення або надішліть медіафайл:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    # Переходимо до стану очікування повідомлення
    return BROADCAST_WAIT_MESSAGE


async def broadcast_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text
    sender_id = update.effective_user.id
    target_data = context.user_data.get('broadcast_target')

    # 1. Визначаємо список отримувачів за цільовою аудиторією
    all_target_ids = get_broadcast_users(target_data, db)  # ВИКОРИСТОВУЄМО ДОПОМІЖНУ ФУНКЦІЮ
    sent_count = 0

    # 2. Виконуємо розсилку
    for target_id in all_target_ids:
        try:
            if target_id == sender_id: continue

            await context.bot.send_message(
                target_id,
                f"📢 Повідомлення адміністрації:\n\n{message_text}"
            )
            sent_count += 1
        except Exception:
            pass  # Ігноруємо помилки

    # 3. Завершення
    user_role = db.get_user(sender_id)[4]
    await update.message.reply_text(
        f"✅ Розсилка завершена. Відправлено: **{sent_count}** повідомлень (Тільки текст).",
        reply_markup=get_main_keyboard(user_role),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def broadcast_send_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sender_id = update.effective_user.id
    caption_prefix = f"📢 **Повідомлення адміністрації:**"
    print(f"--- BROADCAST_MEDIA DEBUG ---")
    print(f"Text: {update.message.text}")
    print(f"Caption: {update.message.caption}")
    print(f"Has Photo: {bool(update.message.photo)}")
    print(f"-----------------------------")
    # 🎯 КЛЮЧОВЕ ВИПРАВЛЕННЯ: Використовуємо обрану ціль
    target_data = context.user_data.get('broadcast_target')
    all_target_ids = get_broadcast_users(target_data, db)  # ВИКОРИСТОВУЄМО ФУНКЦІЮ ВИБОРУ
    sent_count = 0

    # Обробка підпису (caption)
    original_caption = update.message.caption
    caption = f"{caption_prefix}\n\n{original_caption}" if original_caption else caption_prefix

    # Виконуємо розсилку
    for target_id in all_target_ids:  # Ітеруємо по ID
        try:
            if target_id == sender_id:
                continue

            await context.bot.copy_message(
                chat_id=target_id,  # Використовуємо ID
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
            sent_count += 1
        except Exception:
            pass

    # Завершення
    user_role = db.get_user(sender_id)[4]
    await update.message.reply_text(
        f"✅ Розсилка завершена. Відправлено: **{sent_count}** повідомлень (Медіа з/без підпису).",
        reply_markup=get_main_keyboard(user_role),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Скасовує розсилку."""
    user_id = update.effective_user.id
    user_role = db.get_user(user_id)[4]

    query = update.callback_query
    await query.answer("Розсилку скасовано.")

    # Редагуємо повідомлення, щоб прибрати кнопку "Скасувати"
    await query.edit_message_text(
        "❌ **Масову розсилку скасовано.** Ви повернулися до головного меню.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Надсилаємо головну клавіатуру
    await context.bot.send_message(
        user_id,
        "Головне меню:",
        reply_markup=get_main_keyboard(user_role)
    )

    return ConversationHandler.END


async def create_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_name = update.message.text.strip()
    context.user_data['group_name'] = group_name

    keyboard = [
        [InlineKeyboardButton("👥 Парна група", callback_data="group_type_pair")],
        [InlineKeyboardButton("👥 Групова", callback_data="group_type_group")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")]
    ]

    await update.message.reply_text(
        f"Назва групи: {group_name}\n\nОберіть тип групи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CREATE_GROUP_TYPE


async def show_user_filters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує меню з кнопками для фільтрації користувачів"""
    keyboard = [
        [InlineKeyboardButton("📋 Всі користувачі", callback_data="list_all_users")],
        [InlineKeyboardButton("🧑‍🎓 Список учнів", callback_data="list_by_students")],
        [InlineKeyboardButton("👨‍🏫 Список викладачів", callback_data="list_by_teachers")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text="Оберіть, який список користувачів ви хочете переглянути:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Оберіть, який список користувачів ви хочете переглянути:",
            reply_markup=reply_markup
        )


async def cancel_add_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Додавання уроку скасовано.")
    return ConversationHandler.END

async def cancel_create_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Створення групи скасовано.")
    return ConversationHandler.END


async def add_lesson_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user or user[4] != 'teacher':
        await update.message.reply_text("Ця функція доступна лише викладачам.")
        return ConversationHandler.END

    students = db.get_teacher_students(user_id)
    groups = db.get_teacher_groups(user_id)

    if not students and not groups:
        await update.message.reply_text("У вас ще немає учнів та груп.")
        return ConversationHandler.END

    keyboard = []

    for student in students:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🎓 {student[2]} {student[3]} (індивідуально)",
            callback_data=f"lesson_student_{student[0]}"
        )])

    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"👥 {group[1]} ({group[3]})",
            callback_data=f"lesson_group_{group[0]}"
        )])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_add_lesson")])

    await update.message.reply_text(
        "➕ Додавання уроку\n\nОберіть учня або групу:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_LESSON_STUDENT


async def add_lesson_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()

    try:
        lesson_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        context.user_data['lesson_date'] = lesson_date

        await update.message.reply_text(
            f"📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n\n"
            "Введіть час уроку в форматі ГГ:ХХ:"
        )
        return ADD_LESSON_TIME

    except ValueError:
        await update.message.reply_text("Неправильний формат дати. Введіть в форматі ДД.ММ.РРРР:")
        return ADD_LESSON_DATE


async def add_lesson_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()

    try:
        lesson_time = datetime.strptime(time_text, "%H:%M").time()

        teacher_id = update.effective_user.id
        lesson_date = context.user_data['lesson_date']
        lesson_type = context.user_data.get('lesson_type')

        if lesson_type == 'individual':
            student_id = context.user_data['lesson_student_id']
            lesson_id = db.add_lesson(teacher_id, student_id=student_id,
                                      lesson_date=lesson_date, lesson_time=lesson_time)
            student = db.get_user(student_id)
            target_name = f"{student[2]} {student[3]}"
            teacher = db.get_user(teacher_id)  # Отримуємо дані вчителя

            # --- ВІДПРАВКА В GOOGLE (Індивідуально) ---
            google_row = [
                lesson_date.strftime('%d.%m.%Y'),
                lesson_time.strftime('%H:%M'),
                target_name,
                f"{teacher[2]} {teacher[3]}",
                "Індивідуально"
            ]
            send_to_google("Уроки", google_row)
            # ------------------------------------------

            # Повідомити учня
            try:
                teacher = db.get_user(teacher_id)
                await context.bot.send_message(
                    student_id,
                    f"📚 Новий урок!\n\n"
                    f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
                    f"📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n"
                    f"🕐 Час: {lesson_time.strftime('%H:%M')}"
                )
            except:
                pass
        else:  # group
            group_id = context.user_data['lesson_group_id']
            lesson_id = db.add_lesson(teacher_id, group_id=group_id,
                                      lesson_date=lesson_date, lesson_time=lesson_time)
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == group_id), None)
            target_name = f"групи {group[1] if group else 'Невідомо'}"
            teacher = db.get_user(teacher_id)

            # --- ВІДПРАВКА В GOOGLE (Група) ---
            google_row = [
                lesson_date.strftime('%d.%m.%Y'),
                lesson_time.strftime('%H:%M'),
                "Вся група",
                f"{teacher[2]} {teacher[3]}",
                group[1] if group else "Невідомо"
            ]
            send_to_google("Уроки", google_row)
            # ----------------------------------

            # Повідомити учасників групи
            members = db.get_group_members(group_id)
            teacher = db.get_user(teacher_id)
            for member in members:
                try:
                    await context.bot.send_message(
                        member[0],
                        f"📚 Новий груповий урок!\n\n"
                        f"👥 Група: {group[1] if group else 'Невідомо'}\n"
                        f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
                        f"📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n"
                        f"🕐 Час: {lesson_time.strftime('%H:%M')}"
                    )
                except:
                    pass

        await update.message.reply_text(
            f"✅ Урок додано!\n\n"
            f"📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n"
            f"🕐 Час: {lesson_time.strftime('%H:%M')}\n"
            f"👥 Для: {target_name}"
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Неправильний формат часу. Введіть в форматі ГГ:ХХ:")
        return ADD_LESSON_TIME


async def cancel_admin_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сбрасывает ConversationHandler, удаляет временные данные и возвращает главное меню."""

    user_id = update.effective_user.id

    # --- Очистка временных данных (ОЧЕНЬ ВАЖНО) ---
    keys_to_delete = [k for k in context.user_data.keys() if k.startswith('admin_lesson_')]
    for key in keys_to_delete:
        del context.user_data[key]

    # --- Получение роли и отправка меню ---
    # Вам нужно убедиться, что у вас есть функция db.get_user_role(user_id)
    # Если нет, используйте user[4] из db.get_user(user_id)
    user = db.get_user(user_id)
    user_role = user[4] if user and len(
        user) > 4 else 'admin'  # Предполагаем 'admin' по умолчанию, т.к. это админский диалог

    # Отправка сообщения и главного меню
    if update.message:
        await update.message.reply_text(
            "❌ **Додавання уроку скасовано.**\n\nОберіть наступну дію:",
            reply_markup=get_main_keyboard(user_role),
            parse_mode=ParseMode.MARKDOWN
        )
    # Если это CallbackQuery (хотя fallbacks обрабатывают только MessageHandler,
    # лучше иметь эту проверку для гибкости)
    elif update.callback_query:
        await update.callback_query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ **Додавання уроку скасовано.**\n\nОберіть наступну дію:",
            reply_markup=get_main_keyboard(user_role),
            parse_mode=ParseMode.MARKDOWN
        )

    # 3. Возвращаем END для выхода из диалога
    return ConversationHandler.END

    keyboard = []

    if teacher:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🏫 {teacher[2]} {teacher[3]} (індивідуально)",
            callback_data=f"chat_teacher_{teacher[0]}"
        )])

    for group in groups:
        group_teacher = db.get_user(group[2])
        keyboard.append([InlineKeyboardButton(
            f"👥 {group[1]} (викл: {group_teacher[2] if group_teacher else 'Невідомо'})",
            callback_data=f"chat_group_{group[0]}"
        )])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_chat")])

    await update.message.reply_text(
        "💬 З ким хочете зв'язатися?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def send_full_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, role: Optional[str] = None):
    """Показує повний список користувачів з можливістю фільтрації."""
    if role == 'student':
        users = db.get_users_by_role('student')
        title = "👨‍🎓 Список усіх учнів:"
        icon = "👨‍🎓"
    elif role == 'teacher':
        users = db.get_users_by_role('teacher')
        title = "👨‍🏫 Список усіх викладачів:"
        icon = "👨‍🏫"
    else:
        # Для повного списку потрібно створити нову функцію в класі Database
        # Але поки що використаємо get_users_by_role для 'student' і 'teacher'
        students = db.get_users_by_role('student')
        teachers = db.get_users_by_role('teacher')
        users = students + teachers
        title = "👥 Повний список користувачів:"
        icon = "👥"

    if not users:
        text = f"{title}\n\n❌ Користувачів з такою роллю не знайдено."
    else:
        text = f"{title}\n\n"
        for user_data in users:
            name = f"{user_data[2]} {user_data[3]}"
            role_text = user_data[4]
            text += f"{icon} {name} - {role_text}\n"

    # Додаємо кнопку "Назад"
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Якщо текст занадто довгий, розбиваємо його на частини
    if len(text) > 4096:
        parts = [text[i:i + 4096] for i in range(0, len(text), 4096)]
        for i, part in enumerate(parts):
            if i == len(parts) - 1:  # Останній шматок
                await context.bot.send_message(chat_id=update.effective_chat.id, text=part, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=part)
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
