import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ==========================================
# 1. ІМПОРТ НАЛАШТУВАНЬ ТА КОНСТАНТ
# ==========================================
from config.settings import (
    BOT_TOKEN, SUPER_ADMIN_ID, TRIGGER_WORDS, ALL_MAIN_MENU_BUTTONS_LIST, logger,
    # Імпорт станів ConversationHandler
    REGISTER_NAME, REGISTER_LANG, REGISTER_BIRTHDATE, REGISTER_PHONE,
    ADD_LESSON_STUDENT, ADD_LESSON_DATE, ADD_LESSON_TIME,
    CREATE_GROUP_NAME, CREATE_GROUP_TYPE, CREATE_GROUP_TEACHER, CREATE_GROUP_STUDENTS,
    TEACHER_MESSAGE_SELECT, TEACHER_MESSAGE_TEXT, TEACHER_CHAT_ACTIVE,
    ADMIN_ADD_LESSON_DATE, ADMIN_ADD_LESSON_TIME,
    STUDENT_MESSAGE_SELECT, STUDENT_CHAT_ACTIVE,
    BROADCAST_SELECT_TARGET, BROADCAST_WAIT_MESSAGE
)

# ==========================================
# 2. ІМПОРТ БАЗИ ДАНИХ
# ==========================================
from database.db_manager import db

# ==========================================
# 3. ІМПОРТ ХЕНДЛЕРІВ (Бізнес-логіка)
# ==========================================
# Реєстрація
from handlers.registration import (
    start, register_name, register_language, register_birthdate, register_phone, cancel_registration
)

# Спільні / Глобальні
from handlers.common import (
    common_callbacks, route_manager_contact, fallback_message, handle_unknown_text,
    myid_command, manager_command, handle_history_button
)

# Учень
from handlers.student import (
    student_callbacks, menu_about_school, menu_school_rules, menu_faq, menu_student_calendar,
    show_student_chat_history
)

# Викладач
from handlers.teacher import (
    teacher_callbacks, menu_teacher_schedule, menu_teacher_students, menu_teacher_stats,
    teacher_inbox, show_teacher_groups, teacher_command
)

# Адмін
from handlers.admin import (
    admin_callbacks, menu_admin_groups, menu_admin_chats, menu_admin_schedule,
    menu_admin_users, menu_admin_reports, handle_admin_text_states, init_super_admin,
    admin_command, make_admin_command, remove_admin_command, admin_list_command,
    check_database_command, backup_command, broadcast_start, broadcast_select_target,
    broadcast_send_media, broadcast_send_message, broadcast_cancel, create_group_name,
    add_lesson_start, add_lesson_date, add_lesson_time, admin_add_lesson_date,
    admin_add_lesson_time, cancel_admin_lesson, cancel_add_lesson
)

# Переписки та чати (Тут тепер ВСЯ логіка діалогів)
from handlers.chat_engine import (
    chat_engine_callbacks, student_message_start, quick_reply_start, student_chat_end,
    student_send_media, student_message_text, teacher_message_students,
    teacher_quick_reply_start, teacher_chat_end, teacher_message_text, teacher_send_media
)
# ==========================================
# 4. ІМПОРТ СЕРВІСІВ ТА ФОНОВИХ ЗАДАЧ
# ==========================================
from jobs.scheduler import schedule_daily_reminders, test_reminders_command, force_test_reminders
from services.google_sheets import test_gs, sync_students_command, sync_teachers_command

# Фільтр для кнопок головного меню (щоб виходити з діалогів)
MAIN_MENU_BUTTONS_FILTER = filters.TEXT & filters.Regex(f"^({'|'.join(ALL_MAIN_MENU_BUTTONS_LIST)})$")


# ==========================================
# ГЛОБАЛЬНИЙ ПЕРЕХОПЛЮВАЧ ПОВІДОМЛЕНЬ
# ==========================================
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ця функція ловить тексти, які не є кнопками меню.
    Вона перевіряє права адміна, шукає тригерні слова і кидає невідомий текст у fallback.
    """
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Спочатку зареєструйтеся за допомогою команди /start")
        return

    message_text = update.message.text

    # 1. Перевірка доступу до адмін-кнопок
    admin_buttons = ["👨‍💼 Керування користувачами", "👥 Керування групами", "🗓 Керування розкладом",
                     "🗂️ Переписки / Чати", "📢 Масова розсилка", "📊 Звіти"]
    if message_text in admin_buttons and user[4] != 'admin':
        await update.message.reply_text("❌ У вас немає прав доступу до цієї функції.")
        return

    # 2. Тригерні слова
    for trigger in TRIGGER_WORDS:
        if trigger.lower() in message_text.lower():
            db.save_message(user_id, None, f"[TRIGGER: {trigger}] {message_text}", 'trigger')

    # 3. Fallback (якщо ми не в чаті, значить це невідомий текст)
    if not context.user_data.get('chat_type'):
        await fallback_message(update, context)

    # Обгортка для виклику історії учня


async def route_student_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_student_chat_history(update, context, update.effective_user.id)


def main():
    # 1. Ініціалізація бота
    application = Application.builder().token(BOT_TOKEN).build()

    # 2. Базові налаштування
    init_super_admin()
    schedule_daily_reminders(application)

    # ==========================================
    # 3. CONVERSATION HANDLERS (ДІАЛОГИ)
    # ==========================================
    registration_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],

            # ВИПРАВЛЕНО ТУТ:
            REGISTER_LANG: [
                # Натискання кнопки має вести саме в register_language
                CallbackQueryHandler(register_language, pattern="^lang_"),
                # Якщо користувач замість кнопки надіслав текст — нагадуємо натиснути кнопку
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_language)
            ],

            REGISTER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_birthdate)],
            REGISTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration), CommandHandler('start', start)],
        allow_reentry=True
    )

    add_lesson_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^➕ Додати урок'), add_lesson_start)],
        states={
            ADD_LESSON_STUDENT: [CallbackQueryHandler(admin_callbacks, pattern="^(lesson_student|lesson_group)")],
            ADD_LESSON_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_date)],
            ADD_LESSON_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_time)],
        },
        fallbacks=[CommandHandler('cancel', cancel_add_lesson)],
    )

    create_group_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callbacks, pattern="^create_group$")],
        states={
            CREATE_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_group_name)],
            CREATE_GROUP_TYPE: [CallbackQueryHandler(admin_callbacks, pattern="^group_type_")],
            CREATE_GROUP_TEACHER: [CallbackQueryHandler(admin_callbacks, pattern="^select_group_teacher_")],
            CREATE_GROUP_STUDENTS: [
                CallbackQueryHandler(admin_callbacks, pattern="^(toggle_student|student_page|finish_create)")],
        },
        fallbacks=[CallbackQueryHandler(admin_callbacks, pattern="^cancel_create_group$")],
    )

    teacher_message_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^💬 Написати учневі/групі'), teacher_message_students),
            CallbackQueryHandler(teacher_quick_reply_start, pattern=r'^inbox_reply_\d+$'),
        ],
        states={
            TEACHER_MESSAGE_SELECT: [CallbackQueryHandler(chat_engine_callbacks, pattern="^teacher_chat_")],
            TEACHER_CHAT_ACTIVE: [
                MessageHandler(filters.Regex(r'^Завершити діалог'), teacher_chat_end),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^Завершити діалог'),
                               teacher_message_text),
                MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
                               teacher_send_media)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(teacher_callbacks, pattern="^cancel_teacher_chat$"),
            CommandHandler('cancel', teacher_chat_end),
            CommandHandler('start', teacher_chat_end),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, teacher_chat_end),
        ],
        allow_reentry=True,
    )

    student_message_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^💬 Написати викладачеві/групі'), student_message_start),
            CallbackQueryHandler(quick_reply_start, pattern=r'^quick_reply_(teacher|group)_\d+$'),
        ],
        states={
            STUDENT_MESSAGE_SELECT: [CallbackQueryHandler(chat_engine_callbacks, pattern="^student_chat_")],
            STUDENT_CHAT_ACTIVE: [
                MessageHandler(filters.Regex(r'^Завершити діалог'), student_chat_end),
                MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
                               student_send_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^Завершити діалог'),
                               student_message_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(student_callbacks, pattern="^cancel_student_chat$"),
            CommandHandler('cancel', student_chat_end),
            CommandHandler('start', student_chat_end),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, student_chat_end),
        ],
        allow_reentry=True,
    )

    admin_lesson_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_callbacks,
                                 pattern="^(admin_add_lesson_|admin_select_lesson_|admin_lesson_target_|admin_student_|admin_group_)"),
        ],
        states={
            ADMIN_ADD_LESSON_DATE: [
                MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_admin_lesson),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_lesson_date),
            ],
            ADMIN_ADD_LESSON_TIME: [
                MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_admin_lesson),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_lesson_time),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin_lesson)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^📢 Масова розсилка$'), broadcast_start)],
        states={
            BROADCAST_SELECT_TARGET: [CallbackQueryHandler(broadcast_select_target, pattern="^bc_target_")],
            BROADCAST_WAIT_MESSAGE: [
                MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
                               broadcast_send_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send_message),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(broadcast_cancel, pattern="^cancel_broadcast$"),
            CommandHandler('cancel', broadcast_cancel),
        ],
    )

    # Додаємо діалоги в диспетчер
    application.add_handler(registration_conv)
    application.add_handler(add_lesson_conv)
    application.add_handler(create_group_conv)
    application.add_handler(teacher_message_conv)
    application.add_handler(admin_lesson_conv)
    application.add_handler(student_message_conv)
    application.add_handler(broadcast_conv)

    # ==========================================
    # 4. ОБРОБНИКИ ТЕКСТОВИХ КНОПОК МЕНЮ
    # ==========================================
    application.add_handler(MessageHandler(filters.Regex('^🏫 Про школу$'), menu_about_school))
    application.add_handler(MessageHandler(filters.Regex('^📋 Правила школи$'), menu_school_rules))
    application.add_handler(MessageHandler(filters.Regex('^❓ Популярні питання$'), menu_faq))
    application.add_handler(MessageHandler(filters.Regex('^🗓 Мій календар$'), menu_student_calendar))
    application.add_handler(MessageHandler(filters.Regex('^📖 Історія переписок$'), handle_history_button))

    application.add_handler(MessageHandler(filters.Regex('^📆 Мій розклад$'), menu_teacher_schedule))
    application.add_handler(MessageHandler(filters.Regex('^👨‍🎓 Мої учні$'), menu_teacher_students))
    application.add_handler(MessageHandler(filters.Regex('^📚 Мої групи$'), show_teacher_groups))
    application.add_handler(MessageHandler(filters.Regex('^📊 Статистика$'), menu_teacher_stats))
    application.add_handler(MessageHandler(filters.Regex('^📬 Вхідні$'), teacher_inbox))

    application.add_handler(MessageHandler(filters.Regex('^👥 Керування групами$'), menu_admin_groups))
    application.add_handler(MessageHandler(filters.Regex('^🗂️ Переписки / Чати$'), menu_admin_chats))
    application.add_handler(MessageHandler(filters.Regex('^🗓 Керування розкладом$'), menu_admin_schedule))
    application.add_handler(MessageHandler(filters.Regex('^👨‍💼 Керування користувачами$'), menu_admin_users))
    application.add_handler(MessageHandler(filters.Regex('^📊 Звіти$'), menu_admin_reports))

    application.add_handler(MessageHandler(filters.Regex('^📞 Написати менеджеру$'), route_manager_contact))

    # ==========================================
    # 5. ОБРОБНИКИ КОМАНД (Commands)
    # ==========================================
    application.add_handler(CommandHandler('admin', admin_command))
    application.add_handler(CommandHandler('manager', manager_command))
    application.add_handler(CommandHandler('teacher', teacher_command))
    application.add_handler(CommandHandler('check_db', check_database_command))
    application.add_handler(CommandHandler('test_now', force_test_reminders))
    application.add_handler(CommandHandler("test_gs", test_gs))
    application.add_handler(CommandHandler('sync_students', sync_students_command))
    application.add_handler(CommandHandler('sync_teachers', sync_teachers_command))
    application.add_handler(CommandHandler('test_reminders', test_reminders_command))
    application.add_handler(CommandHandler('add_new_admin', make_admin_command))
    application.add_handler(CommandHandler('remove_admin', remove_admin_command))
    application.add_handler(CommandHandler('admin_list', admin_list_command))
    application.add_handler(CommandHandler('myid', myid_command))
    application.add_handler(CommandHandler("backup", backup_command))

    # ==========================================
    # 6. ІНЛАЙН РОУТЕРИ (Замість старого button_callback)
    # ==========================================
    application.add_handler(
        CallbackQueryHandler(student_callbacks, pattern='^(student_schedule|back_student_schedule)'))

    application.add_handler(
        CallbackQueryHandler(teacher_callbacks, pattern='^(inbox|schedule|back_schedule|back_to_schedule)'))

    # Оновлений роутер для чатів: тепер він ловить все, що містить "chat"
    # (chat_, teacher_chat_, student_chat_, view_chat_ тощо)
    application.add_handler(
        CallbackQueryHandler(chat_engine_callbacks, pattern=r'.*chat.*'))

    # Оновлюємо патерн для адміна, додавши чіткі префікси для викладачів
    application.add_handler(CallbackQueryHandler(
        admin_callbacks,
        pattern='^(admin|toggle|confirm|list|edit|change|assign|add|remove|manage|back_admin|back_groups|group_type|select_group|select_teacher|assign_to_student|student_page|finish_create|cancel_create)'
    ))

    application.add_handler(CallbackQueryHandler(common_callbacks, pattern='^(ignore|back_to_menu|lang_|cal_)'))

    # ==========================================
    # 7. РЕЗЕРВНІ ОБРОБНИКИ ТЕКСТУ ТА МЕДІА
    # ==========================================
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text_states))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))

    print("🚀 Бот запущено...")
    print(f"👑 Головний адміністратор: ID {SUPER_ADMIN_ID}")
    print("📅 Автоматические напоминания об уроках настроены на 8:00")

    application.run_polling()


if __name__ == '__main__':
    main()