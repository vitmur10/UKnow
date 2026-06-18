import sqlite3
import os
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from utils.keyboards import get_main_keyboard, get_broadcast_target_keyboard
from utils.helpers import format_lesson_time, format_lesson_date_time, get_broadcast_users
from services.google_sheets import send_to_google
from services.backup_service import create_backup

from config.settings import (
    SUPER_ADMIN_ID, DB_NAME, BACKUP_DIR, GOOGLE_SCRIPT_URL,
    ADMIN_ADD_LESSON_DATE, ADMIN_ADD_LESSON_TIME,
    CREATE_GROUP_NAME, CREATE_GROUP_TYPE, CREATE_GROUP_TEACHER, CREATE_GROUP_STUDENTS,
    BROADCAST_SELECT_TARGET, BROADCAST_WAIT_MESSAGE, ADD_LESSON_TIME, ADD_LESSON_STUDENT, ADD_LESSON_DATE,
    MESSAGES_PER_PAGE
)


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
        cursor.execute('''SELECT l.lesson_date,
                                 l.lesson_time,
                                 t.first_name,
                                 t.last_name,
                                 s.first_name,
                                 s.last_name,
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

    data = query.data
    # Прінт №1: Що саме натиснув адмін
    print(f"DEBUG BROADCAST: Target selected: {data}")

    context.user_data['broadcast_target'] = data

    if data == 'bc_target_students_all':
        target_name = "Учні: ВСІ"
    elif data == 'bc_target_teachers_all':
        target_name = "Викладачі: ВСІ"
    else:
        print(f"DEBUG BROADCAST: ERROR! Unknown target: {data}")  # Прінт помилки
        await query.edit_message_text("Помилка вибору цілі.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton("❌ Скасувати розсилку", callback_data="cancel_broadcast")]]

    await query.edit_message_text(
        f"🎯 **Ціль обрано:** {target_name}.\n\n"
        "Тепер введіть повідомлення або надішліть медіафайл:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    # Прінт №2: Чи перейшов бот у стан очікування повідомлення
    print(f"DEBUG BROADCAST: State changed to BROADCAST_WAIT_MESSAGE. Waiting for input...")

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
    print(f"\n--- DEBUG: Виклик send_full_user_list ---")
    print(f"Аргумент role: {role}")

    # Визначаємо, чи це натискання на кнопку
    query = update.callback_query
    if query:
        print(f"Викликано через callback_data: {query.data}")
        # Якщо роль не прийшла як аргумент, спробуємо дістати її з callback_data
        if not role and "_" in query.data:
            role = query.data.split("_")[-1]
            print(f"Роль вилучена з callback: {role}")

    if role == 'student':
        users = db.get_users_by_role('student')
        title = "👨‍🎓 Список усіх учнів:"
        icon = "👨‍🎓"
    elif role == 'teacher':
        users = db.get_users_by_role('teacher')
        title = "👨‍🏫 Список усіх викладачів:"
        icon = "👨‍🏫"
    else:
        print("Отримуємо всіх користувачів (студенти + викладачі)")
        students = db.get_users_by_role('student') or []
        teachers = db.get_users_by_role('teacher') or []
        users = students + teachers
        title = "👥 Повний список користувачів:"
        icon = "👥"

    print(f"Знайдено користувачів у БД: {len(users) if users else 0}")

    if not users:
        text = f"{title}\n\n❌ Користувачів з такою роллю не знайдено."
    else:
        text = f"{title}\n\n"
        for user_data in users:
            try:
                # Виводимо в консоль сирі дані, щоб бачити структуру
                # print(f"DEBUG USER DATA: {user_data}")
                name = f"{user_data[2]} {user_data[3]}"
                role_text = user_data[4]
                text += f"{icon} {name} - {role_text}\n"
            except Exception as e:
                print(f"Помилка при обробці user_data {user_data}: {e}")

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_users")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    print(f"Довжина тексту повідомлення: {len(text)} символів")

    try:
        if len(text) > 4096:
            print("Текст занадто довгий, розбиваємо на частини...")
            parts = [text[i:i + 4096] for i in range(0, len(text), 4096)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=part,
                                                   reply_markup=reply_markup)
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=part)
        else:
            if query:
                print("Спроба редагування існуючого повідомлення...")
                await query.answer()
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:
                print("Відправка нового повідомлення...")
                await update.message.reply_text(text, reply_markup=reply_markup)
        print("--- DEBUG: Повідомлення успішно відправлено ---\n")
    except Exception as e:
        print(f"!!! ПОМИЛКА ПРИ ВІДПРАВЦІ: {e}")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # ПРИМІТКА: Припускається, що змінна 'db' (інстанс Database) доступна глобально
    user = db.get_user(user_id)

    # Обмеження доступу (тільки для адміністраторів або супер-адміна)
    if not user or (user[4] != 'admin' and user_id != SUPER_ADMIN_ID):
        await update.message.reply_text("❌ У вас немає прав доступу до цієї команди.")
        return

    await update.message.reply_text("⏳ Створюю резервну копію бази даних...")

    backup_path = await create_backup(DB_NAME, BACKUP_DIR)

    if backup_path and os.path.exists(backup_path):
        try:
            with open(backup_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    caption=f"✅ Резервна копія створена: `{os.path.basename(backup_path)}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            # Видалення локальної копії
            os.remove(backup_path)
            await update.message.reply_text("ℹ️ Локальна копія файлу бази даних була видалена.")
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка надсилання файлу: {e}")
    else:
        await update.message.reply_text("❌ Не вдалося створити резервну копію.")


async def admin_add_lesson_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()

    try:
        lesson_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        context.user_data['admin_lesson_date'] = lesson_date

        await update.message.reply_text(
            f"📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n\n"
            "Введіть час уроку в форматі ГГ:ХХ:"
        )
        return ADMIN_ADD_LESSON_TIME

    except ValueError:
        await update.message.reply_text("Неправильний формат дати. Введіть в форматі ДД.ММ.РРРР:")
        return ADMIN_ADD_LESSON_DATE


# 3. ИСПРАВЛЕНИЕ: Исправить функцию admin_add_lesson_time
async def admin_add_lesson_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()

    try:
        # 1. Обробка часу
        lesson_time = datetime.strptime(time_text, "%H:%M").time()

        # 2. Отримання даних із контексту
        teacher_id = context.user_data['admin_lesson_teacher_id']
        lesson_date = context.user_data['admin_lesson_date']
        entity_type = context.user_data['admin_lesson_entity_type']
        entity_id = context.user_data['admin_lesson_entity_id']

        # 3. Додавання в базу та сповіщення
        if entity_type == "student":
            db.add_lesson(teacher_id, student_id=entity_id,
                          lesson_date=lesson_date, lesson_time=lesson_time)
            student = db.get_user(entity_id)
            target_name = f"учня {student[2]} {student[3]}"

            try:
                teacher = db.get_user(teacher_id)
                await context.bot.send_message(
                    entity_id,
                    f"📚 Новий урок!\n\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n🕐 Час: {lesson_time.strftime('%H:%M')}"
                )
            except:
                pass

        elif entity_type == "group":
            db.add_lesson(teacher_id, group_id=entity_id,
                          lesson_date=lesson_date, lesson_time=lesson_time)
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == entity_id), None)
            target_name = f"групи {group[1] if group else 'Невідомо'}"

            members = db.get_group_members(entity_id)
            teacher = db.get_user(teacher_id)
            for member in members:
                try:
                    await context.bot.send_message(
                        member[0],
                        f"📚 Новий груповий урок!\n\n👥 Група: {group[1] if group else 'Невідомо'}\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n🕐 Час: {lesson_time.strftime('%H:%M')}"
                    )
                except:
                    pass
        else:
            target_name = "Невідомо"

        # 4. Сповіщення викладача
        try:
            await context.bot.send_message(
                teacher_id,
                f"📚 Новий урок додано адміністратором!\n\n📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n🕐 Час: {lesson_time.strftime('%H:%M')}\n👥 Для: {target_name}"
            )
        except:
            pass

        # 5. Запис у Google Таблицю
        try:
            teacher = db.get_user(teacher_id)
            teacher_full_name = f"{teacher[2]} {teacher[3]}" if teacher else "Невідомо"
            google_row = [
                lesson_date.strftime('%d.%m.%Y'),
                lesson_time.strftime('%H:%M'),
                target_name.replace("учня ", "").replace("групи ", ""),
                teacher_full_name,
                "Додано Адміном"
            ]
            send_to_google("Уроки", google_row)
        except Exception as e:
            print(f"Помилка Google Таблиці: {e}")

        # --- ФІКС КНОПОК ---
        # 1. Кнопка "Додати ще" (залишається як була)
        cb_add_more = f"admin_lesson_target_{entity_type}_{entity_id}"

        # 2. Кнопка "До списку уроків" — ТЕПЕР ВЕДЕ НА РОЗКЛАД
        if entity_type == "student":
            cb_back_to_list = f"admin_student_{entity_id}"
        elif entity_type == "group":
            cb_back_to_list = f"admin_group_{entity_id}"  # Перевірте, чи такий префікс для груп
        else:
            cb_back_to_list = "admin_menu"

        keyboard = [
            [InlineKeyboardButton("➕ Додати ще урок", callback_data=cb_add_more)],
            [InlineKeyboardButton("📋 До списку уроків", callback_data=cb_back_to_list)],
            [InlineKeyboardButton("🏠 Головне меню", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Урок додано!\n\n📅 Дата: {lesson_date.strftime('%d.%m.%Y')}\n🕐 Час: {lesson_time.strftime('%H:%M')}\n👥 Для: {target_name}",
            reply_markup=reply_markup
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Неправильний формат часу. Введіть в форматі ГГ:ХХ:")
        return ADMIN_ADD_LESSON_TIME


# --- ІНЛАЙН КНОПКИ АДМІНА ---
async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Виняток для кнопок пагінації, які нічого не роблять
    if query.data == "ignore":
        await query.answer()
        return

    await query.answer()
    data = query.data

    # ==========================================
    # 1. МУЛЬТИ-СКАСУВАННЯ УРОКІВ
    # ==========================================
    if data.startswith("admin_cancel_") or data.startswith("toggle_multi_") or data.startswith(
            "toggle_teacher_") or data.startswith("toggle_group_") or data.startswith("confirm_multi_"):

        if data.startswith("admin_cancel_student_") or data.startswith("toggle_multi_"):
            print(f"\n[DEBUG] Вхід в блок скасування. Data: {data}")
            parts = data.split("_")

            if data.startswith("toggle_multi_"):
                student_id = int(parts[3])
                clicked_lesson_id = parts[2]
                selected_ids = parts[4].split(":") if len(parts) > 4 and parts[4] else []

                print(f"[DEBUG] Клікнули по уроку ID: {clicked_lesson_id}")
                if clicked_lesson_id in selected_ids:
                    selected_ids.remove(clicked_lesson_id)
                    print(f"[DEBUG] Видалили урок зі списку. Тепер обрано: {selected_ids}")
                else:
                    selected_ids.append(clicked_lesson_id)
                    print(f"[DEBUG] Додали урок до списку. Тепер обрано: {selected_ids}")
            else:
                student_id = int(parts[3])
                selected_ids = []
                print(f"[DEBUG] Перший вхід для учня ID: {student_id}")

            student = db.get_user(student_id)
            lessons = db.get_active_lessons_for_student(student_id)

            if not lessons:
                await query.edit_message_text(f"❌ У учня {student[2]} {student[3]} немає активних уроків.")
                return

            keyboard = []
            selected_str = ":".join(selected_ids)

            for lesson in lessons:
                lesson_id = str(lesson[0])
                is_selected = lesson_id in selected_ids
                mark = "✅ " if is_selected else ""

                l_date = lesson[4] if len(lesson) > 4 else "??.??"
                l_time = lesson[5][:5] if len(lesson) > 5 and lesson[5] else "??:??"

                t_first = lesson[9] if len(lesson) > 9 and lesson[9] else ""
                t_last = lesson[10] if len(lesson) > 10 and lesson[10] else ""
                t_name = f"{t_first} {t_last}".strip() or f"Викл (ID: {lesson[6]})"

                if lesson[2]:
                    lesson_text = f"{mark}📚 {l_date} о {l_time} — викл: {t_name}"
                else:
                    g_name = lesson[13] if len(lesson) > 13 and lesson[13] else "Група"
                    lesson_text = f"{mark}👥 {l_date} о {l_time} — гр: {g_name}"

                keyboard.append([InlineKeyboardButton(lesson_text,
                                                      callback_data=f"toggle_multi_{lesson_id}_{student_id}_{selected_str}")])

            if selected_ids:
                final_callback = f"confirm_multi_cancel_{student_id}_{selected_str}"
                print(f"[DEBUG] Генеруємо кнопку скасування. Callback: {final_callback}")
                keyboard.append(
                    [InlineKeyboardButton(f"🔥 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})", callback_data=final_callback)])

            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_student_{student_id}")])

            text = f"🗑 **Мульти-скасування для {student[2]} {student[3]}**\n\nОберіть уроки (натисніть ще раз, щоб зняти вибір):"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        elif data.startswith("admin_cancel_teacher_") or data.startswith("toggle_teacher_"):
            parts = data.split("_")
            if data.startswith("toggle_teacher_"):
                teacher_id = int(parts[3])
                clicked_lesson_id = parts[2]
                selected_ids = parts[4].split(":") if len(parts) > 4 and parts[4] else []
                if clicked_lesson_id in selected_ids:
                    selected_ids.remove(clicked_lesson_id)
                else:
                    selected_ids.append(clicked_lesson_id)
            else:
                teacher_id = int(parts[3])
                selected_ids = []

            teacher = db.get_user(teacher_id)
            lessons = db.get_active_lessons_for_teacher(teacher_id)

            if not lessons:
                await query.edit_message_text(f"❌ У викладача {teacher[2]} {teacher[3]} немає активних уроків.")
                return

            keyboard = []
            selected_str = ":".join(selected_ids)

            for lesson in lessons:
                l_id = str(lesson[0])
                is_selected = l_id in selected_ids
                mark = "✅ " if is_selected else ""

                if lesson[2]:
                    lesson_text = f"{mark}📚 {lesson[3]} {lesson[4]} - уч: {lesson[6]} {lesson[7]}"
                else:
                    lesson_text = f"{mark}👥 {lesson[3]} {lesson[4]} - гр: {lesson[8] or 'Невідомо'}"

                keyboard.append([InlineKeyboardButton(lesson_text,
                                                      callback_data=f"toggle_teacher_{l_id}_{teacher_id}_{selected_str}")])

            if selected_ids:
                keyboard.append([InlineKeyboardButton(f"🗑 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})",
                                                      callback_data=f"confirm_multi_teacher_{teacher_id}_{selected_str}")])

            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_teacher_{teacher_id}")])

            await query.edit_message_text(
                f"🗑 **Скасування уроків викладача {teacher[2]} {teacher[3]}**\n\nОберіть уроки (вибрано: {len(selected_ids)}):",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
            )
            return

        elif data.startswith("admin_cancel_group_") or data.startswith("toggle_group_"):
            parts = data.split("_")
            if data.startswith("toggle_group_"):
                group_id = int(parts[3])
                clicked_lesson_id = parts[2]
                selected_ids = parts[4].split(":") if len(parts) > 4 and parts[4] else []
                if clicked_lesson_id in selected_ids:
                    selected_ids.remove(clicked_lesson_id)
                else:
                    selected_ids.append(clicked_lesson_id)
            else:
                group_id = int(parts[3])
                selected_ids = []

            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == group_id), None)
            lessons = db.get_active_lessons_for_group(group_id)

            if not lessons:
                group_name = group[1] if group else 'Невідомо'
                await query.edit_message_text(f"❌ У групи {group_name} немає активних уроків.")
                return

            keyboard = []
            selected_str = ":".join(selected_ids)

            for lesson in lessons:
                l_id = str(lesson[0])
                is_selected = l_id in selected_ids
                mark = "✅ " if is_selected else ""

                l_date = lesson[4]
                l_time = lesson[5][:5] if lesson[5] else "--:--"
                t_lname = lesson[9] if len(lesson) > 9 else ""

                lesson_text = f"{mark}📚 {l_date} {l_time} - викл: {t_lname}"
                keyboard.append(
                    [InlineKeyboardButton(lesson_text, callback_data=f"toggle_group_{l_id}_{group_id}_{selected_str}")])

            if selected_ids:
                context.user_data['pending_termination_ids'] = selected_ids
                keyboard.append([InlineKeyboardButton(f"🗑 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})",
                                                      callback_data=f"confirm_multi_group_{group_id}")])

            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_group_{group_id}")])

            group_name = group[1] if group else 'Невідомо'
            await query.edit_message_text(
                f"🗑 **Скасування уроків групи {group_name}**\n\nОберіть уроки для видалення:",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
            )
            return

        elif data.startswith("confirm_multi_group_"):
            parts = data.split("_")
            group_id = int(parts[3])
            selected_ids = context.user_data.get('pending_termination_ids', [])

            if not selected_ids:
                await query.answer("❌ Список порожній", show_alert=True)
                return

            group_data = db.get_group_by_id(group_id)
            group_name = group_data[1] if group_data else "Невідома група"
            teacher_id = group_data[2] if group_data else None
            members = db.get_group_members(group_id)

            lessons_to_notify = []
            success_count = 0

            for l_id in selected_ids:
                if not l_id: continue
                try:
                    conn = sqlite3.connect(db.db_name)
                    cursor = conn.cursor()
                    cursor.execute("SELECT lesson_date, lesson_time FROM lessons WHERE id = ?", (int(l_id),))
                    info = cursor.fetchone()
                    conn.close()

                    if info:
                        date_str = datetime.strptime(info[0], '%Y-%m-%d').strftime('%d.%m.%Y')
                        time_str = info[1][:5]
                        lessons_to_notify.append(f"📅 {date_str} о {time_str} (за Києвом)")

                    db.cancel_lesson(int(l_id))
                    success_count += 1
                except Exception as e:
                    pass  # Тут можна додати logger.error(e)

            if success_count > 0:
                lessons_list = "\n".join(lessons_to_notify)
                notification_text = f"❌ **Урок скасовано адміністрацією**\n{lessons_list}\n👥 Група: **{group_name}**"

                for member in members:
                    try:
                        await context.bot.send_message(chat_id=member[0], text=notification_text, parse_mode="Markdown")
                    except:
                        continue

                if teacher_id:
                    try:
                        await context.bot.send_message(chat_id=teacher_id, text=notification_text,
                                                       parse_mode="Markdown")
                    except:
                        pass

            context.user_data['pending_termination_ids'] = []
            await query.edit_message_text(
                f"✅ Успішно скасовано {success_count} уроків. Повідомлення надіслано.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_group_{group_id}")]])
            )
            return

        elif data.startswith("confirm_multi_cancel_"):
            print(f"\n[DEBUG] !!! БОТ ЗЛОВИВ ФІНАЛЬНУ КНОПКУ !!!")
            parts = data.split("_")
            student_id = parts[3]
            lesson_ids = parts[4].split(":")

            print(f"[DEBUG] Починаємо скасування для учня {student_id}. Уроки: {lesson_ids}")
            count = 0

            for l_id in lesson_ids:
                if not l_id: continue

                lesson = db.get_lesson_by_id(int(l_id))
                if not lesson: continue

                db.cancel_lesson(int(l_id))

                # Примітка: переконайся, що функція format_lesson_date_time імпортована
                f_date = lesson[4]  # Заглушка, якщо немає функції
                f_time = lesson[5][:5] if lesson[5] else ""

                t_first = lesson[9] if lesson[9] else ""
                t_last = lesson[10] if lesson[10] else ""
                t_full = f"{t_first} {t_last}".strip() or "Викладач"

                try:
                    if lesson[2]:
                        await context.bot.send_message(
                            lesson[2],
                            f"❌ Урок скасовано адміністрацією\n📅 {f_date} о {f_time}\n👨‍🏫 Викладач: {t_full}"
                        )

                    s_first = lesson[11] if lesson[11] else ""
                    s_last = lesson[12] if lesson[12] else ""
                    s_full = f"{s_first} {s_last}".strip() or "Учень"
                    target = f"👨‍🎓 Учень: {s_full}" if lesson[2] else f"👥 Група: {lesson[13] or 'Невідомо'}"

                    await context.bot.send_message(
                        lesson[1],
                        f"❌ Урок скасовано адміністрацією\n📅 {f_date} о {f_time}\n{target}"
                    )
                except Exception as e:
                    print(f"[DEBUG] Помилка відправки повідомлення: {e}")

                count += 1

            await query.answer(f"✅ Скасовано уроків: {count}", show_alert=True)
            await query.edit_message_text(
                f"✅ Успішно скасовано уроків: **{count}**\n\nВсі учасники отримали повідомлення.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ До розкладу", callback_data=f"admin_student_{student_id}")]]),
                parse_mode="Markdown"
            )
            return

    # ==========================================
    # 2. КЕРУВАННЯ РОЗКЛАДОМ
    # ==========================================
    elif data.startswith("admin_select_") or data.startswith("admin_student_") or data.startswith(
            "admin_teacher_") or data.startswith(
        "admin_group_") or data == "admin_search_student_schedule" or data == "back_admin_schedule" or data.startswith(
        "admin_add_lesson_") or data.startswith("lesson_student_") or data.startswith(
        "lesson_group_") or data == "cancel_add_lesson" or data.startswith("admin_lesson_target_"):

        if data.startswith("admin_select_student"):
            parts = data.split("_")
            try:
                # Намагаємось отримати номер сторінки, якщо елементів більше 3
                page = int(parts[3]) if len(parts) > 3 else 0
            except ValueError:
                # Якщо 4-й елемент — це текст (наприклад, 'page'),
                # безпечно залишаємо 0 за замовчуванням
                page = int(parts[-1]) if parts[-1].isdigit() else 0
            items_per_page = 10

            students = db.get_users_by_role('student')
            if not students:
                await query.edit_message_text("Учеников нет.")
                return

            total_pages = (len(students) + items_per_page - 1) // items_per_page
            start_idx = page * items_per_page
            end_idx = start_idx + items_per_page
            current_students = students[start_idx:end_idx]

            keyboard = []
            for student in current_students:
                teacher = db.get_student_teacher(student[0])
                teacher_info = f" (викл: {teacher[2]} {teacher[3]})" if teacher else " (без викладача)"
                keyboard.append([InlineKeyboardButton(f"👨‍🎓 {student[2]} {student[3]}{teacher_info}",
                                                      callback_data=f"admin_student_{student[0]}")])

            navigation_buttons = []
            if page > 0:
                navigation_buttons.append(
                    InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_select_student_{page - 1}"))
            navigation_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
            if end_idx < len(students):
                navigation_buttons.append(
                    InlineKeyboardButton("Вперед ➡️", callback_data=f"admin_select_student_{page + 1}"))

            if navigation_buttons: keyboard.append(navigation_buttons)
            keyboard.append([InlineKeyboardButton("🔍 Пошук за ім'ям", callback_data="admin_search_student_schedule")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])

            await query.edit_message_text(f"Оберіть учня (всього {len(students)}):",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "admin_search_student_schedule":
            context.user_data['waiting_for_admin_student_search'] = True
            await query.edit_message_text(
                "🔎 Введіть ім'я або прізвище учня (або частину):\n\nБот знайде всіх учнів, у яких є це слово в імені або прізвищі."
            )
            return

        elif data == "admin_select_teacher":
            teachers = db.get_users_by_role('teacher')
            if not teachers:
                await query.edit_message_text("Викладачів немає.")
                return
            keyboard = []
            for teacher in teachers:
                students_count = len(db.get_teacher_students(teacher[0]))
                groups_count = len(db.get_teacher_groups(teacher[0]))
                keyboard.append([InlineKeyboardButton(
                    f"👨‍🏫 {teacher[2]} {teacher[3]} ({students_count} учнів, {groups_count} груп)",
                    callback_data=f"admin_teacher_{teacher[0]}")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])
            await query.edit_message_text("Оберіть викладача:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "admin_select_group":
            groups = db.get_all_groups()
            if not groups:
                await query.edit_message_text("Груп немає.")
                return
            keyboard = []
            for group in groups:
                teacher = db.get_user(group[2])
                members_count = len(db.get_group_members(group[0]))
                keyboard.append([InlineKeyboardButton(
                    f"👥 {group[1]} (викл: {teacher[2] if teacher else 'Невідомо'}, {members_count} учнів)",
                    callback_data=f"admin_group_{group[0]}")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])
            await query.edit_message_text("Оберіть групу:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("admin_student_"):
            student_id = int(data.split("_")[2])
            student = db.get_user(student_id)
            lessons = db.get_active_lessons_for_student(student_id)
            student_full_name = f"{student[2] or ''} {student[3] or ''}".strip()

            if not lessons:
                text = f"📅 Розклад учня {student_full_name}\n\n❌ Активних уроків немає"
            else:
                text = f"📅 Розклад учня {student_full_name}\n\n"
                for lesson in lessons[:15]:
                    l_date = lesson[4]
                    l_time = lesson[5][:5] if lesson[5] else "??:??"
                    t_id = lesson[1]
                    teacher = db.get_user(t_id)
                    if teacher:
                        t_full = f"{teacher[2] or ''} {teacher[3] or ''}".strip()
                    else:
                        t_first = lesson[9] if len(lesson) > 9 and lesson[9] else ""
                        t_last = lesson[10] if len(lesson) > 10 and lesson[10] else ""
                        t_full = f"{t_first} {t_last}".strip() or "Викладач"
                    text += f"📚 {l_date} о {l_time} — викладач: {t_full}\n"

            keyboard = [
                [InlineKeyboardButton("➕ Додати урок", callback_data=f"admin_add_lesson_student_{student_id}")],
                [InlineKeyboardButton("🗑 Скасувати урок", callback_data=f"admin_cancel_student_{student_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin_select_student")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("admin_teacher_"):
            teacher_id = int(data.split("_")[2])
            teacher = db.get_user(teacher_id)
            lessons = db.get_active_lessons_for_teacher(teacher_id)
            teacher_full_name = f"{teacher[2] or ''} {teacher[3] or ''}".strip()

            if not lessons:
                text = f"📅 Розклад викладача {teacher_full_name}\n\n❌ Уроків немає"
            else:
                text = f"📅 Розклад викладача {teacher_full_name}\n\n"
                for lesson in lessons[:15]:
                    l_date = lesson[4]
                    l_time = lesson[5][:5] if lesson[5] else "??:??"

                    if lesson[2]:
                        s_id = lesson[2]
                        student = db.get_user(s_id)
                        s_full = f"{student[2] or ''} {student[3] or ''}".strip() if student else "Учень"
                        text += f"📚 {l_date} о {l_time} — з: {s_full}\n"
                    elif lesson[3]:
                        g_id = lesson[3]
                        group_data = db.get_group(g_id)
                        g_name = group_data[1] if group_data else (
                            lesson[11] if len(lesson) > 11 and lesson[11] else "Група")
                        text += f"📚 {l_date} о {l_time} — з: {g_name}\n"
                    else:
                        text += f"📚 {l_date} о {l_time} — з: Невідомо\n"

            keyboard = [
                [InlineKeyboardButton("➕ Додати урок", callback_data=f"admin_add_lesson_teacher_{teacher_id}")],
                [InlineKeyboardButton("🗑 Скасувати урок", callback_data=f"admin_cancel_teacher_{teacher_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin_select_teacher")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("admin_group_"):
            group_id = int(data.split("_")[2])
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == group_id), None)
            lessons = db.get_active_lessons_for_group(group_id)
            group_name = group[1] if group else "???"

            if not lessons:
                text = f"📅 Розклад групи {group_name}\n\n❌ Уроків немає"
            else:
                text = f"📅 Розклад групи {group_name}\n\n"
                for lesson in lessons[:15]:
                    l_date = lesson[4]
                    l_time = lesson[5][:5] if lesson[5] else "??:??"
                    status_icon = "❌" if lesson[7] == 'cancelled' else "📚"

                    t_id = lesson[1]
                    teacher = db.get_user(t_id)
                    t_full = f"{teacher[2] or ''} {teacher[3] or ''}".strip() if teacher else (
                            f"{lesson[9] or ''} {lesson[10] or ''}".strip() or "Викладач")
                    text += f"{status_icon} {l_date} о {l_time} — викладач: {t_full}\n"

            keyboard = [
                [InlineKeyboardButton("➕ Додати урок", callback_data=f"admin_add_lesson_group_{group_id}")],
                [InlineKeyboardButton("🗑 Скасувати урок", callback_data=f"admin_cancel_group_{group_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin_select_group")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("admin_add_lesson_"):
            parts = data.split("_")
            entity_type = parts[3]
            entity_id = int(parts[4])

            context.user_data['admin_lesson_entity_type'] = entity_type
            context.user_data['admin_lesson_entity_id'] = entity_id

            if entity_type == "student":
                student = db.get_user(entity_id)
                teacher = db.get_student_teacher(entity_id)
                if not teacher:
                    await query.edit_message_text("❌ У учня немає призначеного викладача.")
                    return
                context.user_data['admin_lesson_teacher_id'] = teacher[0]
                await query.edit_message_text(
                    f"➕ Додавання уроку для учня {student[2]} {student[3]}\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:"
                )
            elif entity_type == "teacher":
                teacher = db.get_user(entity_id)
                context.user_data['admin_lesson_teacher_id'] = entity_id

                students = db.get_teacher_students(entity_id)
                groups = db.get_teacher_groups(entity_id)

                if not students and not groups:
                    await query.edit_message_text("❌ У викладача немає учнів та груп.")
                    return

                keyboard = []
                for student in students:
                    keyboard.append([InlineKeyboardButton(f"👨‍🎓 {student[2]} {student[3]}",
                                                          callback_data=f"admin_select_lesson_student_{student[0]}")])
                for group in groups:
                    keyboard.append(
                        [InlineKeyboardButton(f"👥 {group[1]}", callback_data=f"admin_select_lesson_group_{group[0]}")])
                keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"admin_teacher_{entity_id}")])

                await query.edit_message_text(
                    f"➕ Додавання уроку для викладача {teacher[2]} {teacher[3]}\n\nОберіть учня або групу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            elif entity_type == "group":
                groups = db.get_all_groups()
                group = next((g for g in groups if g[0] == entity_id), None)
                if not group:
                    await query.edit_message_text("❌ Група не знайдена.")
                    return
                context.user_data['admin_lesson_teacher_id'] = group[2]
                await query.edit_message_text(
                    f"➕ Додавання уроку для групи {group[1]}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:"
                )
            # ВАЖЛИВО: Оскільки це стан ConversationHandler, переконайся, що функція повертає правильну змінну.
            from main import ADMIN_ADD_LESSON_DATE
            return ADMIN_ADD_LESSON_DATE

        elif data.startswith("admin_select_lesson_"):
            parts = data.split("_")
            target_type = parts[3]
            target_id = int(parts[4])

            context.user_data['admin_lesson_target_type'] = target_type
            context.user_data['admin_lesson_target_id'] = target_id
            context.user_data['admin_lesson_entity_type'] = target_type
            context.user_data['admin_lesson_entity_id'] = target_id

            if target_type == "student":
                student = db.get_user(target_id)
                teacher = db.get_user(context.user_data['admin_lesson_teacher_id'])
                await query.edit_message_text(
                    f"➕ Додавання уроку\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n👨‍🎓 Учень: {student[2]} {student[3]}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:"
                )
            else:
                groups = db.get_all_groups()
                group = next((g for g in groups if g[0] == target_id), None)
                teacher = db.get_user(context.user_data['admin_lesson_teacher_id'])
                await query.edit_message_text(
                    f"➕ Додавання уроку\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n👥 Група: {group[1] if group else 'Невідомо'}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:"
                )
            from main import ADMIN_ADD_LESSON_DATE
            return ADMIN_ADD_LESSON_DATE

        elif data == "back_admin_schedule":
            keyboard = [
                [InlineKeyboardButton("👨‍🎓 Обрати учня", callback_data="admin_select_student")],
                [InlineKeyboardButton("👨‍🏫 Обрати викладача", callback_data="admin_select_teacher")],
                [InlineKeyboardButton("👥 Обрати групу", callback_data="admin_select_group")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text("🗓 Керування розкладом\n\nОберіть тип пошуку:",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("lesson_student_"):
            student_id = int(data.split("_")[2])
            context.user_data['lesson_student_id'] = student_id
            context.user_data['lesson_type'] = 'individual'
            student = db.get_user(student_id)
            await query.edit_message_text(
                f"➕ Додавання уроку для {student[2]} {student[3]}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:")
            from main import ADD_LESSON_DATE
            return ADD_LESSON_DATE

        elif data.startswith("lesson_group_"):
            group_id = int(data.split("_")[2])
            context.user_data['lesson_group_id'] = group_id
            context.user_data['lesson_type'] = 'group'
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == group_id), None)
            await query.edit_message_text(
                f"➕ Додавання уроку для групи {group[1] if group else 'Невідомо'}\n\nВведіть дату уроку в форматі ДД.ММ.РРРР:")
            from main import ADD_LESSON_DATE
            return ADD_LESSON_DATE

        elif data == "cancel_add_lesson":
            await query.edit_message_text("Додавання уроку скасовано.")
            return ConversationHandler.END

        elif data.startswith("admin_lesson_target_"):
            parts = data.split("_")
            try:
                entity_type = parts[3]
                entity_id = int(parts[4])
                context.user_data['admin_lesson_entity_type'] = entity_type
                context.user_data['admin_lesson_entity_id'] = entity_id

                target_label = "учня" if entity_type == "student" else "групи"
                await query.edit_message_text(
                    f"➕ Додавання ще одного уроку для {target_label}.\n\nВведіть дату уроку (ДД.ММ.РРРР):")
                from main import ADMIN_ADD_LESSON_DATE
                return ADMIN_ADD_LESSON_DATE
            except (IndexError, ValueError) as e:
                print(f"Помилка парсингу admin_lesson_target: {e}")
                await query.answer("Сталася помилка. Спробуйте через меню.", show_alert=True)
                return ConversationHandler.END


    # ==========================================
    # 3. КЕРУВАННЯ ГРУПАМИ
    # ==========================================
    elif data in ["list_groups", "edit_group", "back_groups", "create_group", "finish_create_group",
                  "cancel_create_group"] or data.startswith("edit_group_") or (
            data.startswith("change_teacher_") and not data.startswith(
        "change_teacher_for_student_")) or data.startswith("set_teacher_") or data.startswith(
        "manage_members_") or data.startswith("add_member_") or data.startswith("add_student_") or data.startswith(
        "remove_member_") or data.startswith("group_type_") or data.startswith(
        "select_group_teacher_") or data.startswith("toggle_student_") or data.startswith("student_page_"):

        if data == "create_group":
            await query.edit_message_text("Введіть назву групи:")
            context.user_data['creating_group'] = True
            from main import CREATE_GROUP_NAME
            return CREATE_GROUP_NAME

        elif data == "list_groups":
            groups = db.get_all_groups()
            if not groups:
                text = "👥 Список всіх груп:\n\n❌ Груп поки немає"
            else:
                text = "👥 Список всіх груп:\n\n"
                for group in groups:
                    teacher = db.get_user(group[2])
                    members = db.get_group_members(group[0])
                    text += f"📚 {group[1]} ({group[3]})\n"
                    text += f"👨‍🏫 Викладач: {teacher[2]} {teacher[3] if teacher else 'Невідомо'}\n"
                    text += f"👥 Учасників: {len(members)}\n\n"

            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_groups")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "edit_group":
            groups = db.get_all_groups()
            if not groups:
                await query.edit_message_text("Груп для редагування немає.")
                return
            keyboard = []
            for group in groups:
                keyboard.append(
                    [InlineKeyboardButton(f"✏️ {group[1]} ({group[3]})", callback_data=f"edit_group_{group[0]}")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_groups")])
            await query.edit_message_text("Оберіть групу для редагування:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("edit_group_"):
            group_id = int(data.split("_")[2])
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == group_id), None)

            keyboard = [
                [InlineKeyboardButton("👨‍🏫 Змінити викладача", callback_data=f"change_teacher_{group_id}")],
                [InlineKeyboardButton("👥 Керування учасниками", callback_data=f"manage_members_{group_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="edit_group")]
            ]
            await query.edit_message_text(f"✏️ Редагування групи: {group[1] if group else 'Невідомо'}\n\nОберіть дію:",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("change_teacher_") and not data.startswith("change_teacher_for_student_"):
            parts = data.split("_")
            group_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0

            teachers = db.get_users_by_role('teacher')
            if not teachers:
                await query.edit_message_text("Немає доступних викладачів.")
                return

            PAGE_SIZE = 10
            total_pages = (len(teachers) + PAGE_SIZE - 1) // PAGE_SIZE
            start = page * PAGE_SIZE
            chunk = teachers[start: start + PAGE_SIZE]

            keyboard = []
            for t in chunk:
                keyboard.append(
                    [InlineKeyboardButton(f"👨‍🏫 {t[2]} {t[3]}", callback_data=f"set_teacher_{group_id}_{t[0]}")])

            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"change_teacher_{group_id}_{page - 1}"))
            nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ignore"))
            if (start + PAGE_SIZE) < len(teachers):
                nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"change_teacher_{group_id}_{page + 1}"))
            if nav: keyboard.append(nav)

            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"edit_group_{group_id}")])
            await query.edit_message_text(f"Оберіть нового викладача (Сторінка {page + 1}):",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("set_teacher_"):
            parts = data.split("_")
            group_id = int(parts[2])
            teacher_id = int(parts[3])

            db.change_group_teacher(group_id, teacher_id)
            teacher = db.get_user(teacher_id)
            keyboard = [[InlineKeyboardButton("🔙 Назад до меню групи", callback_data=f"edit_group_{group_id}")]]
            await query.edit_message_text(f"✅ Викладача групи змінено на: {teacher[2]} {teacher[3]}",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("manage_members_"):
            group_id = int(data.split("_")[2])
            members = db.get_group_members(group_id)
            group = db.get_group(group_id)

            keyboard = [[InlineKeyboardButton("➕ Додати учасника", callback_data=f"add_member_{group_id}_0")]]
            for member in members:
                keyboard.append([InlineKeyboardButton(f"❌ Видалити {member[2]} {member[3]}",
                                                      callback_data=f"remove_member_{group_id}_{member[0]}")])
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edit_group_{group_id}")])

            await query.edit_message_text(f"👥 Керування групою: {group[1]}\nУчасників: {len(members)}",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("add_member_"):
            parts = data.split("_")
            group_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0

            students = db.get_users_by_role('student')
            current_members = [m[0] for m in db.get_group_members(group_id)]
            available_students = [s for s in students if s[0] not in current_members]

            if not available_students:
                await query.edit_message_text("Немає доступних учнів для додавання.", reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Назад", callback_data=f"manage_members_{group_id}")]]))
                return

            PAGE_SIZE = 10
            total_pages = (len(available_students) + PAGE_SIZE - 1) // PAGE_SIZE
            chunk = available_students[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

            keyboard = []
            for student in chunk:
                keyboard.append([InlineKeyboardButton(f"👨‍🎓 {student[2]} {student[3]}",
                                                      callback_data=f"add_student_{group_id}_{student[0]}_{page}")])

            nav = []
            if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"add_member_{group_id}_{page - 1}"))
            nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ignore"))
            if (page + 1) * PAGE_SIZE < len(available_students): nav.append(
                InlineKeyboardButton("➡️", callback_data=f"add_member_{group_id}_{page + 1}"))
            if nav: keyboard.append(nav)

            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"manage_members_{group_id}")])
            await query.edit_message_text(f"Оберіть учня (Стор. {page + 1} з {total_pages}):",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("add_student_"):
            parts = data.split("_")
            group_id, student_id, page = int(parts[2]), int(parts[3]), int(parts[4])
            db.add_student_to_group(group_id, student_id)
            student = db.get_user(student_id)
            keyboard = [[InlineKeyboardButton("🔙 Додати ще учнів", callback_data=f"add_member_{group_id}_{page}")],
                        [InlineKeyboardButton("✅ Готово", callback_data=f"manage_members_{group_id}")]]
            await query.edit_message_text(f"✅ Учня {student[2]} {student[3]} додано!",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("remove_member_"):
            parts = data.split("_")
            group_id, student_id = int(parts[2]), int(parts[3])
            db.remove_student_from_group(group_id, student_id)
            data = f"manage_members_{group_id}"  # Це буде відловлено, якщо ти викличеш функцію знову, або можна зробити редірект
            # Краще зробити прямий виклик чи оновлення:
            await query.answer("Учасника видалено")
            # Тут потрібна логіка повернення до меню manage_members_
            return

        elif data == "back_groups":
            keyboard = [
                [InlineKeyboardButton("➕ Створити групу", callback_data="create_group")],
                [InlineKeyboardButton("👥 Список груп", callback_data="list_groups")],
                [InlineKeyboardButton("✏️ Змінити групу", callback_data="edit_group")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ]
            await query.edit_message_text("👥 Керування групами\n\nОберіть дію:",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data.startswith("group_type_"):
            group_type = data.split("_")[2]
            context.user_data['group_type'] = group_type
            teachers = db.get_users_by_role('teacher')
            if not teachers:
                await query.edit_message_text("Немає доступних викладачів.")
                return ConversationHandler.END
            keyboard = []
            for teacher in teachers:
                keyboard.append([InlineKeyboardButton(f"👨‍🏫 {teacher[2]} {teacher[3]}",
                                                      callback_data=f"select_group_teacher_{teacher[0]}")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])
            await query.edit_message_text(
                f"Група: {context.user_data['group_name']} ({group_type})\n\nОберіть викладача:",
                reply_markup=InlineKeyboardMarkup(keyboard))
            from main import CREATE_GROUP_TEACHER
            return CREATE_GROUP_TEACHER

        elif data.startswith("select_group_teacher_"):
            teacher_id = int(data.split("_")[3])
            context.user_data['group_teacher_id'] = teacher_id
            context.user_data['selected_students'] = []
            context.user_data['current_page'] = 0

            teacher = db.get_user(teacher_id)
            students = db.get_users_by_role('student')

            if not students:
                await query.edit_message_text("Немає доступних учнів.")
                return ConversationHandler.END

            PAGE_SIZE = 10
            current_students_chunk = students[0:PAGE_SIZE]
            keyboard = []
            for student in current_students_chunk:
                keyboard.append([InlineKeyboardButton(f"👨‍🎓 {student[2]} {student[3]}",
                                                      callback_data=f"toggle_student_{student[0]}")])
            if len(students) > PAGE_SIZE:
                keyboard.append([InlineKeyboardButton("Вперед ➡️", callback_data="student_page_1")])

            keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])
            await query.edit_message_text(
                f"Група: {context.user_data['group_name']}\nВикладач: {teacher[2]} {teacher[3]}\n\nОберіть учнів (сторінка 1):",
                reply_markup=InlineKeyboardMarkup(keyboard))
            from main import CREATE_GROUP_STUDENTS
            return CREATE_GROUP_STUDENTS

        elif data.startswith("toggle_student_"):
            student_id = int(data.split("_")[2])
            selected = context.user_data.get('selected_students', [])
            current_page = context.user_data.get('current_page', 0)

            if student_id in selected:
                selected.remove(student_id)
            else:
                selected.append(student_id)
            context.user_data['selected_students'] = selected

            students = db.get_users_by_role('student')
            PAGE_SIZE = 10
            start = current_page * PAGE_SIZE
            end = start + PAGE_SIZE
            current_students_chunk = students[start:end]

            keyboard = []
            for student in current_students_chunk:
                is_selected = student[0] in selected
                prefix = "✅ " if is_selected else "👨‍🎓 "
                keyboard.append([InlineKeyboardButton(f"{prefix}{student[2]} {student[3]}",
                                                      callback_data=f"toggle_student_{student[0]}")])

            nav_buttons = []
            if current_page > 0: nav_buttons.append(
                InlineKeyboardButton("⬅️ Назад", callback_data=f"student_page_{current_page - 1}"))
            if end < len(students): nav_buttons.append(
                InlineKeyboardButton("Вперед ➡️", callback_data=f"student_page_{current_page + 1}"))
            if nav_buttons: keyboard.append(nav_buttons)

            keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])

            teacher = db.get_user(context.user_data['group_teacher_id'])
            selected_names = [f"{db.get_user(s_id)[2]} {db.get_user(s_id)[3]}" for s_id in selected if
                              db.get_user(s_id)]

            text = (
                f"Група: {context.user_data['group_name']}\nВикладач: {teacher[2]} {teacher[3]}\nОбрано учнів: {len(selected)}\nСторінка: {current_page + 1}\n")
            if selected_names: text += f"Учні: {', '.join(selected_names)}\n"
            text += "\nОберіть учнів (можна обрати декілька):"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            from main import CREATE_GROUP_STUDENTS
            return CREATE_GROUP_STUDENTS

        elif data.startswith("student_page_"):
            current_page = int(data.split("_")[2])
            context.user_data['current_page'] = current_page
            selected = context.user_data.get('selected_students', [])

            students = db.get_users_by_role('student')
            PAGE_SIZE = 10
            start = current_page * PAGE_SIZE
            end = start + PAGE_SIZE
            current_students_chunk = students[start:end]

            keyboard = []
            for student in current_students_chunk:
                is_selected = student[0] in selected
                prefix = "✅ " if is_selected else "👨‍🎓 "
                keyboard.append([InlineKeyboardButton(f"{prefix}{student[2]} {student[3]}",
                                                      callback_data=f"toggle_student_{student[0]}")])

            nav_buttons = []
            if current_page > 0: nav_buttons.append(
                InlineKeyboardButton("⬅️ Назад", callback_data=f"student_page_{current_page - 1}"))
            if end < len(students): nav_buttons.append(
                InlineKeyboardButton("Вперед ➡️", callback_data=f"student_page_{current_page + 1}"))
            if nav_buttons: keyboard.append(nav_buttons)

            keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])

            teacher = db.get_user(context.user_data['group_teacher_id'])
            text = (
                f"Група: {context.user_data['group_name']}\nВикладач: {teacher[2]} {teacher[3]}\nОбрано учнів: {len(selected)}\nСторінка: {current_page + 1}\n\nОберіть учнів:")
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            from main import CREATE_GROUP_STUDENTS
            return CREATE_GROUP_STUDENTS

        elif data == "finish_create_group":
            selected_students = context.user_data.get('selected_students', [])
            if not selected_students:
                await query.edit_message_text("❌ Потрібно обрати хоча б одного учня.")
                from main import CREATE_GROUP_STUDENTS
                return CREATE_GROUP_STUDENTS

            group_id = db.create_group(context.user_data['group_name'], context.user_data['group_teacher_id'],
                                       context.user_data['group_type'])
            for student_id in selected_students:
                db.add_student_to_group(group_id, student_id)

            teacher = db.get_user(context.user_data['group_teacher_id'])
            await query.edit_message_text(
                f"✅ Групу створено!\n\n📚 Назва: {context.user_data['group_name']}\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n👥 Учнів: {len(selected_students)}")

            try:
                await context.bot.send_message(context.user_data['group_teacher_id'],
                                               f"👥 Вам призначено нову групу: {context.user_data['group_name']}")
            except:
                pass

            for student_id in selected_students:
                try:
                    await context.bot.send_message(student_id,
                                                   f"👥 Вас додано до групи: {context.user_data['group_name']}\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}")
                except:
                    pass

            return ConversationHandler.END

        elif data == "cancel_create_group":
            await query.edit_message_text("Створення групи скасовано.")
            return ConversationHandler.END

    # ==========================================
    # 4. КОРИСТУВАЧІ ТА ПРИЗНАЧЕННЯ
    # ==========================================
    elif data in ["list_by_teachers", "list_all_users", "back_to_admin_users", "list_users", "list_by_students",
                  "assign_teacher", "add_teacher", "show_user_filters_menu"] or any(
        data.startswith(prefix) for prefix in
        ["change_student_teacher", "change_teacher_for_student_", "assign_new_teacher_",
         "remove_teacher_from_student_", "select_teacher_", "assign_to_student_"]):

        # 1. Прості команди
        if data == "list_by_teachers":
            await send_full_user_list(update, context, role='teacher')
            return

        elif data == "list_all_users":
            await send_full_user_list(update, context)
            return

        elif data in ["back_to_admin_users", "list_users", "show_user_filters_menu"]:
            await show_user_filters_menu(update, context)
            return

        elif data == "list_by_students":
            await send_full_user_list(update, context, role='student')
            return

        # 2. Додавання викладача (ID)
        elif data == "add_teacher":
            await query.edit_message_text("Введіть ID користувача, якого хочете зробити викладачем:")
            context.user_data['waiting_for_teacher_id'] = True
            return

        # 3. Призначення викладача (Початок - вибір викладача)
        elif data == "assign_teacher":
            teachers = db.get_users_by_role('teacher')
            if not teachers:
                await query.edit_message_text("Немає викладачів для призначення.")
                return
            keyboard = []
            for teacher in teachers:
                keyboard.append([InlineKeyboardButton(f"👨‍🏫 {teacher[2]} {teacher[3]}",
                                                      callback_data=f"select_teacher_{teacher[0]}")])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_to_menu")])
            await query.edit_message_text("🔗 Призначити викладача\n\nОберіть викладача:",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # 4. Обробка вибору викладача
        if data.startswith("select_teacher_") and not data.startswith("select_teacher_students_page_"):
            try:
                parts = data.split("_")
                teacher_id = int(parts[2])
                context.user_data['selected_teacher_id'] = teacher_id
                # Оновлюємо data для переходу в наступний блок
                data = f"select_teacher_students_page_{teacher_id}_0"
            except Exception as e:
                await query.edit_message_text(f"❌ Помилка в select_teacher: {e}")
                return

        # 5. Відображення списку учнів
        if data.startswith("select_teacher_students_page_"):
            try:
                parts = data.split("_")
                # Частини: [4] - ID, [5] - Page
                teacher_id = int(parts[4])
                page = int(parts[5]) if len(parts) > 5 else 0

                context.user_data['selected_teacher_id'] = teacher_id
                teacher = db.get_user(teacher_id)

                if not teacher:
                    await query.edit_message_text(f"❌ Викладача з ID {teacher_id} не знайдено.")
                    return

                students = db.get_users_by_role('student')
                if not students:
                    await query.edit_message_text("Немає учнів для призначення.")
                    return

                items_per_page = 10
                total_pages = (len(students) + items_per_page - 1) // items_per_page
                start_idx = page * items_per_page
                current_students = students[start_idx: start_idx + items_per_page]

                keyboard = []
                for student in current_students:
                    keyboard.append([InlineKeyboardButton(
                        f"👨‍🎓 {student[2]} {student[3]}",
                        callback_data=f"assign_to_student_{student[0]}"
                    )])

                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Назад",
                                                            callback_data=f"select_teacher_students_page_{teacher_id}_{page - 1}"))

                nav_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))

                if (start_idx + items_per_page) < len(students):
                    nav_buttons.append(InlineKeyboardButton("Вперед ➡️",
                                                            callback_data=f"select_teacher_students_page_{teacher_id}_{page + 1}"))

                if nav_buttons:
                    keyboard.append(nav_buttons)

                keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_to_menu")])

                await query.edit_message_text(
                    f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n\nОберіть учня (сторінка {page + 1} з {total_pages}):",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            except Exception as e:
                await query.edit_message_text(f"❌ Помилка в списку учнів: {e}")
                return

        # 6. Фінальне призначення
        elif data.startswith("assign_to_student_"):
            # Тут індекс має бути 3, якщо callback "assign_to_student_ID"
            student_id = int(data.split("_")[3])
            teacher_id = context.user_data.get('selected_teacher_id')

            if not teacher_id:
                await query.edit_message_text("Помилка: викладач не обраний. Почніть спочатку.")
                return

            try:
                db.assign_teacher_to_student(teacher_id, student_id)
                teacher = db.get_user(teacher_id)
                student = db.get_user(student_id)

                await query.edit_message_text(
                    f"✅ Призначення завершено!\n\n👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n👨‍🎓 Учень: {student[2]} {student[3]}")

                for target_id, text in [(teacher_id, f"👨‍🎓 Вам призначено нового учня:\n{student[2]} {student[3]}"),
                                        (student_id, f"👨‍🏫 Вам призначено викладача:\n{teacher[2]} {teacher[3]}")]:
                    try:
                        await context.bot.send_message(target_id, text)
                    except:
                        pass
            except Exception as e:
                await query.edit_message_text(f"❌ Помилка призначення: {str(e)}")
            return

        # 7. Зміна викладача учня (Вибір учня зі сторінками)
        elif data.startswith("change_student_teacher"):
            parts = data.split("_")
            try:
                # Намагаємось отримати номер сторінки, якщо елементів більше 3
                page = int(parts[3]) if len(parts) > 3 else 0
            except ValueError:
                # Якщо 4-й елемент — це текст (наприклад, 'page'),
                # безпечно залишаємо 0 за замовчуванням
                page = int(parts[-1]) if parts[-1].isdigit() else 0
            items_per_page = 10

            students = db.get_users_by_role('student')
            if not students:
                await query.edit_message_text("Немає учнів.")
                return

            total_pages = (len(students) + items_per_page - 1) // items_per_page
            start_idx = page * items_per_page
            current_students = students[start_idx: start_idx + items_per_page]

            keyboard = []
            for student in current_students:
                # Отримуємо інформацію про поточного вчителя
                teacher = db.get_student_teacher(student[0])
                teacher_info = f" (викл: {teacher[2]} {teacher[3]})" if teacher else " (без викладача)"
                keyboard.append([InlineKeyboardButton(
                    f"👨‍🎓 {student[2]} {student[3]}{teacher_info}",
                    callback_data=f"change_teacher_for_student_{student[0]}"
                )])

            # Навігація
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Назад", callback_data=f"change_student_teacher_page_{page - 1}"))
            nav_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
            if (start_idx + items_per_page) < len(students):
                nav_buttons.append(
                    InlineKeyboardButton("Вперед ➡️", callback_data=f"change_student_teacher_page_{page + 1}"))

            if nav_buttons: keyboard.append(nav_buttons)
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_users")])

            await query.edit_message_text(f"🔄 Оберіть учня (сторінка {page + 1}):",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # 8. Вибір нового вчителя для конкретного учня
        elif data.startswith("change_teacher_for_student_"):
            student_id = int(data.split("_")[4])
            student = db.get_user(student_id)
            current_teacher = db.get_student_teacher(student_id)

            teachers = db.get_users_by_role('teacher')
            # Відфільтровуємо того, хто вже призначений
            available_teachers = [t for t in teachers if not current_teacher or t[0] != current_teacher[0]]

            keyboard = []
            if current_teacher:
                keyboard.append([InlineKeyboardButton("🗑 Прибрати викладача",
                                                      callback_data=f"remove_teacher_from_student_{student_id}")])

            for t in available_teachers:
                keyboard.append([InlineKeyboardButton(f"👨‍🏫 {t[2]} {t[3]}",
                                                      callback_data=f"assign_new_teacher_{student_id}_{t[0]}")])

            keyboard.append([InlineKeyboardButton("⬅️ До учнів", callback_data="change_student_teacher")])

            txt = f"🔄 Зміна викладача для {student[2]} {student[3]}\n"
            txt += f"Зараз: {current_teacher[2]} {current_teacher[3]}" if current_teacher else "Зараз: без викладача"

            await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # 9. Фінальне перепризначення зі сповіщеннями
        elif data.startswith("assign_new_teacher_"):
            parts = data.split("_")
            student_id, new_teacher_id = int(parts[3]), int(parts[4])

            old_teacher = db.get_student_teacher(student_id)
            db.assign_teacher_to_student(new_teacher_id, student_id)

            student = db.get_user(student_id)
            new_teacher = db.get_user(new_teacher_id)

            await query.edit_message_text(f"✅ Успішно змінено!\n👨‍🎓 {student[2]} ➡️ 👨‍🏫 {new_teacher[2]}")

            # Сповіщення (копіюємо з вашої старої версії)
            for cid, msg in [
                (new_teacher_id, f"👨‍🎓 Новий учень: {student[2]} {student[3]}"),
                (student_id, f"👨‍🏫 Ваш новий викладач: {new_teacher[2]} {new_teacher[3]}"),
            ]:
                try:
                    await context.bot.send_message(cid, msg)
                except:
                    pass
            return

        # 10. Видалення призначення
        elif data.startswith("remove_teacher_from_student_"):
            student_id = int(data.split("_")[4])
            # Тут використовуйте ваш метод видалення (через SQL або db.remove_assignment)
            # Приклад через SQL як у вас було:
            import sqlite3
            conn = sqlite3.connect(db.db_name)
            conn.execute("UPDATE assignments SET is_active = 0 WHERE student_id = ?", (student_id,))
            conn.commit()
            conn.close()

            await query.edit_message_text("✅ Викладача прибрано. Учень тепер без вчителя.")
            return


# --- СТЕЙТИ (ОЧІКУВАННЯ ТЕКСТУ ВІД АДМІНА) ---
# Це код з кінця твого handle_message, який чекає на введення тексту (ID, ім'я, дату)
async def handle_admin_text_states(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    user = db.get_user(update.effective_user.id)
    # Обробка додавання викладача за ID
    if context.user_data.get('waiting_for_teacher_id') and user[4] == 'admin':
        try:
            teacher_id = int(message_text)
            target_user = db.get_user(teacher_id)

            if target_user:
                conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET role = 'teacher' WHERE user_id = ?", (teacher_id,))
                conn.commit()
                conn.close()

                await update.message.reply_text(
                    f"✅ Користувач {target_user[2]} {target_user[3]} тепер викладач!"
                )

                # Повідомити нового викладача
                try:
                    await context.bot.send_message(
                        teacher_id,
                        "🎉 Вітаємо! Ви стали викладачем!",
                        reply_markup=get_main_keyboard('teacher')
                    )
                except:
                    pass
            else:
                await update.message.reply_text("❌ Користувач з таким ID не знайдений.")
        except ValueError:
            await update.message.reply_text("❌ Неправильний ID. Введіть число.")

        context.user_data['waiting_for_teacher_id'] = False
        return
    # Обробка пошуку учня для розкладу (адмін)
    elif context.user_data.get('waiting_for_admin_student_search') and user[4] == 'admin':
        context.user_data['waiting_for_admin_student_search'] = False
        search_query = message_text.strip().lower()
        students = db.get_users_by_role('student')
        found = [
            s for s in students
            if search_query in (s[2] or "").lower() or search_query in (s[3] or "").lower()
        ]
        if not found:
            keyboard = [
                [InlineKeyboardButton("🔍 Спробувати ще раз", callback_data="admin_search_student_schedule")],
                [InlineKeyboardButton("📋 До списку учнів", callback_data="admin_select_student_0")]
            ]
            await update.message.reply_text(
                f"❌ Нікого не знайдено за запитом «{update.message.text}».",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            keyboard = []
            for student in found:
                teacher = db.get_student_teacher(student[0])
                teacher_info = f" (викл: {teacher[2]} {teacher[3]})" if teacher else " (без викладача)"
                keyboard.append([InlineKeyboardButton(
                    f"👨‍🎓 {student[2]} {student[3]}{teacher_info}",
                    callback_data=f"admin_student_{student[0]}"
                )])
            keyboard.append([InlineKeyboardButton("🔍 Новий пошук", callback_data="admin_search_student_schedule")])
            keyboard.append([InlineKeyboardButton("📋 До списку учнів", callback_data="admin_select_student_0")])
            await update.message.reply_text(
                f"🔎 Знайдено учнів: {len(found)}\n\nОберіть учня:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    # Обробка введення дати для історії чатів
    elif context.user_data.get('waiting_for_date') and user[4] == 'admin':
        try:
            date_obj = datetime.strptime(message_text.strip(), "%d.%m.%Y").date()
            date_str = date_obj.strftime('%Y-%m-%d')

            # Отримуємо всі повідомлення за дату
            # модальное окно
            conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''SELECT m.*, u.first_name, u.last_name
                              FROM messages m
                                       JOIN users u ON m.from_user_id = u.user_id
                              WHERE date (m.timestamp) = ?
                              ORDER BY m.timestamp DESC''', (date_str,))
            messages = cursor.fetchall()
            conn.close()

            context.user_data['waiting_for_date'] = False

            if not messages:
                text = f"📅 Повідомлення за {date_obj.strftime('%d.%m.%Y')}\n\n❌ Повідомлень немає"
                await update.message.reply_text(text)
                return

            context.user_data['current_chat_messages'] = messages
            context.user_data['current_chat_title'] = f"📅 Повідомлення за {date_obj.strftime('%d.%m.%Y')}"
            context.user_data['current_page'] = 0
            context.user_data['current_chat_entity_type'] = "date_filter"

            ## Формуємо текст для першої сторінки
            total_messages = len(messages)
            total_pages = (total_messages + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE
            page_messages = messages[:MESSAGES_PER_PAGE]

            text = f"📅 Повідомлення за {date_obj.strftime('%d.%m.%Y')}\n\n"
            if total_pages > 1:
                text += f"(Сторінка 1 з {total_pages})\n\n"

            for msg in page_messages:
                try:
                    if len(msg) >= 9:
                        timestamp = datetime.fromisoformat(msg[6]).strftime("%d.%m %H:%M")
                        sender_name = f"{msg[7]} {msg[8]}" if msg[7] and msg[8] else "Невідомо"

                        # Оновлена логіка вибору тексту повідомлення
                        # рыть туточки
                        # if msg[3]: # Перевірка на group_id
                        if msg[4]:
                            message_text = str(msg[4]) if msg[4] else ""
                        else:
                            message_text = str(msg[3]) if msg[3] else ""

                        # это первич отрисовка окна после поиска по дате с данными (без сообщен)
                        # вставить полн текст сообщ сюда
                        # календарик 📅 жулик
                        text += f"📅[{timestamp}] {sender_name}: {message_text} \n"
                    else:
                        text += f"Повідомлення: {msg}\n"

                except Exception as e:
                    print(f"Error processing message: {msg}, error: {e}")
                    continue

            # Формуємо клавіатуру з кнопками пагінації
            keyboard_row = []
            if total_pages > 1:
                keyboard_row.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"chat_page_1"))
            keyboard = [
                keyboard_row,
                [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_chat_menu")]
            ]

            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        except ValueError:
            await update.message.reply_text("❌ Неправильний формат дати. Використовуйте ДД.ММ.РРРР")
            context.user_data['waiting_for_date'] = False
            return
    # === БЛОК ПОШУКУ КОРИСТУВАЧІВ ТА ГРУП ===
    elif context.user_data.get('waiting_for_search_name'):
        search_query = update.message.text.strip().lower()
        chat_type = context.user_data.get('search_chat_type', 'student')

        # Вимикаємо режим очікування відразу, щоб наступні повідомлення не потрапляли сюди
        context.user_data['waiting_for_search_name'] = False

        found_items = []
        label = "👨‍🎓"
        prefix = "view_chat_student"

        # Логіка пошуку залежно від типу чату
        if chat_type == "group":
            label, prefix = "👥", "view_chat_group"
            all_groups = db.get_all_groups()
            found_items = [g for g in all_groups if search_query in g[1].lower()]
        else:
            # Для студентів або вчителів
            users = db.get_users_by_role(chat_type)
            label = "👨‍🎓" if chat_type == "student" else "👨‍🏫"
            prefix = "view_chat_student" if chat_type == "student" else "view_chat_teacher"

            found_items = [
                u for u in users
                if search_query in (u[2] or "").lower() or search_query in (u[3] or "").lower()
            ]

        # Якщо нікого не знайшли
        if not found_items:
            keyboard = [[InlineKeyboardButton("🔍 Спробувати ще раз", callback_data=f"search_chat_user_{chat_type}")]]
            keyboard.append([InlineKeyboardButton("🔙 До списку", callback_data=f"chat_by_{chat_type}_0")])

            await update.message.reply_text(
                f"❌ Нікого не знайдено за запитом '{update.message.text}'.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Формуємо список кнопок
        keyboard = []
        for item in found_items:
            if chat_type == "group":
                # В таблиці groups: 0:id, 1:name
                name = item[1]
            else:
                # В таблиці users: 0:id, 2:first_name, 3:last_name
                name = f"{item[2] or ''} {item[3] or ''}".strip() or "Без імені"

            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{item[0]}")])

        # Кнопка повернення
        keyboard.append([InlineKeyboardButton("🔙 Назад до повного списку", callback_data=f"chat_by_{chat_type}_0")])

        await update.message.reply_text(
            f"✅ Знайдено {len(found_items)} результатів за запитом '{update.message.text}':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    else:
        # Якщо нічого не підійшло, кидаємо у fallback (невідомий текст)
        from handlers.common import fallback_message
        await fallback_message(update, context)


async def menu_admin_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Створити групу", callback_data="create_group")],
        [InlineKeyboardButton("👥 Список груп", callback_data="list_groups")],
        [InlineKeyboardButton("✏️ Змінити групу", callback_data="edit_group")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("👥 Керування групами\n\nОберіть дію:", reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_admin_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨‍🎓 По учню", callback_data="chat_by_student_0")],
        [InlineKeyboardButton("👨‍🏫 По викладачу", callback_data="chat_by_teacher_0")],
        [InlineKeyboardButton("👥 По групі", callback_data="chat_by_group_0")],
        [InlineKeyboardButton("📅 По даті", callback_data="chat_by_date")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("🗂️ Переписки / Чати\n\nОберіть спосіб фільтрації:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_admin_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨‍🎓 Обрати учня", callback_data="admin_select_student")],
        [InlineKeyboardButton("👨‍🏫 Обрати викладача", callback_data="admin_select_teacher")],
        [InlineKeyboardButton("👥 Обрати групу", callback_data="admin_select_group")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("🗓 Керування розкладом\n\nОберіть тип пошуку:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨‍🏫 Додати викладача", callback_data="add_teacher")],
        [InlineKeyboardButton("🔗 Призначити викладача", callback_data="assign_teacher")],
        [InlineKeyboardButton("🔄 Змінити викладача учня", callback_data="change_student_teacher")],
        [InlineKeyboardButton("📋 Список користувачів", callback_data="show_user_filters_menu")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    await update.message.reply_text("👨‍💼 Керування користувачами\n\nОберіть дію:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_admin_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    students_count = len(db.get_users_by_role('student'))
    teachers_count = len(db.get_users_by_role('teacher'))
    groups_count = len(db.get_all_groups())

    await update.message.reply_text(
        f"📊 Звіти системи:\n\n"
        f"👨‍🎓 Учнів: {students_count}\n"
        f"👨‍🏫 Викладачів: {teachers_count}\n"
        f"👥 Груп: {groups_count}\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )