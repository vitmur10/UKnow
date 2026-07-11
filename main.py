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
    # Стани ConversationHandler (чати більше НЕ використовують стани!)
    REGISTER_NAME, REGISTER_LANG, REGISTER_BIRTHDATE, REGISTER_PHONE,
    ADD_LESSON_STUDENT, ADD_LESSON_DATE, ADD_LESSON_TIME,
    CREATE_GROUP_NAME, CREATE_GROUP_TYPE, CREATE_GROUP_TEACHER, CREATE_GROUP_STUDENTS,
    ADMIN_ADD_LESSON_DATE, ADMIN_ADD_LESSON_TIME,
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
    myid_command, manager_command, handle_history_button, show_media_gallery
)

# Учень
from handlers.student import (
    student_callbacks, show_student_chat_history
)

# Викладач
from handlers.teacher import (
    teacher_callbacks, teacher_command
)

# Адмін
from handlers.admin import (
    admin_callbacks, handle_admin_text_states, init_super_admin,
    admin_command, make_admin_command, remove_admin_command, admin_list_command,
    check_database_command, backup_command, broadcast_start, broadcast_select_target,
    broadcast_send_media, broadcast_send_message, broadcast_cancel, create_group_name,
    add_lesson_start, add_lesson_date, add_lesson_time, admin_add_lesson_date,
    admin_add_lesson_time, cancel_admin_lesson, cancel_add_lesson
)

# Двигун чатів (БЕЗ ConversationHandler — стан у context.user_data)
from handlers.chat_engine import (
    chat_engine_callbacks, student_message_start, teacher_message_students,
    quick_reply_start, teacher_quick_reply_start, chat_end,
    menu_button_router, relay_chat_message, get_active_chat
)

# ==========================================
# 4. ІМПОРТ СЕРВІСІВ ТА ФОНОВИХ ЗАДАЧ
# ==========================================
from jobs.scheduler import schedule_daily_reminders, test_reminders_command, force_test_reminders
from services.google_sheets import test_gs, sync_students_command, sync_teachers_command

# Фільтр для кнопок головного меню (щоб виходити з діалогів)
MAIN_MENU_BUTTONS_FILTER = filters.TEXT & filters.Regex(f"^({'|'.join(ALL_MAIN_MENU_BUTTONS_LIST)})$")

# Фільтр медіа для глобального обробника
MEDIA_FILTER = (
    filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO |
    filters.VOICE | filters.VIDEO_NOTE | filters.ANIMATION | filters.Sticker.ALL
)


# ==========================================
# ГЛОБАЛЬНИЙ ПЕРЕХОПЛЮВАЧ ТЕКСТОВИХ ПОВІДОМЛЕНЬ
# ==========================================
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Єдиний маршрутизатор текстових повідомлень.

    Порядок перевірки:
    1. Реєстрація користувача.
    2. Тригерні слова (журналюються завжди).
    3. АКТИВНИЙ ЧАТ (context.user_data) — повідомлення миттєво пересилається
       співрозмовнику через relay_chat_message. Це заміна ConversationHandler
       для чатів: користувач ніколи не "застрягає" у стані.
    4. Адмін-стани (handle_admin_text_states).
    5. Невідомий текст.
    """
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Спочатку зареєструйтеся за допомогою команди /start")
        return

    message_text = update.message.text or ""

    # Кнопки головного меню ловить окремий хендлер (menu_button_router),
    # сюди вони потрапити не повинні. Про всяк випадок — просто виходимо.
    if MAIN_MENU_BUTTONS_FILTER.check_update(update):
        return

    # Тригерні слова — журналюємо завжди (навіть у активному чаті)
    for trigger in TRIGGER_WORDS:
        if trigger.lower() in message_text.lower():
            db.save_message(user_id, None, None, f"[TRIGGER: {trigger}] {message_text}", 'trigger')

    # АКТИВНИЙ ЧАТ: миттєве пересилання
    if get_active_chat(context):
        await relay_chat_message(update, context)
        return

    # Пошук користувача за ім'ям (історія переписок)
    if context.user_data.get('waiting_for_search_name'):
        await fallback_message(update, context)
        return

    # Адмін-стани
    handled = await handle_admin_text_states(update, context)
    if handled:
        return

    # Невідомий текст
    await handle_unknown_text(update, context)


# ==========================================
# ГЛОБАЛЬНИЙ ПЕРЕХОПЛЮВАЧ МЕДІА
# ==========================================
async def global_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробляє фото/відео/документи/аудіо/голосові/стікери поза ConversationHandler.
    Якщо у користувача активний чат — файл миттєво пересилається співрозмовнику
    (кожен файл альбому окремо, без буферизації — нічого не губиться).
    """
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        return

    if get_active_chat(context):
        await relay_chat_message(update, context)
        return

    # Медіа поза чатом — підказуємо користувачу, що робити
    await handle_unknown_text(update, context)


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
    # УВАГА: діалоги чатів (teacher_message_conv / student_message_conv)
    # ВИДАЛЕНО — чати працюють через глобальні обробники + context.user_data.
    # ==========================================
    registration_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_LANG: [
                CallbackQueryHandler(register_language, pattern="^lang_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_language)
            ],
            REGISTER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_birthdate)],
            REGISTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_registration),
            CommandHandler('start', start),
        ],
        allow_reentry=True
    )

    add_lesson_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^➕ Додати урок'), add_lesson_start)],
        states={
            ADD_LESSON_STUDENT: [CallbackQueryHandler(admin_callbacks, pattern="^(lesson_student|lesson_group)")],
            ADD_LESSON_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_date)],
            ADD_LESSON_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_time)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_add_lesson),
            CommandHandler('start', cancel_add_lesson),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_add_lesson),
        ],
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
        fallbacks=[
            CallbackQueryHandler(admin_callbacks, pattern="^cancel_create_group$"),
            CommandHandler('start', start),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, start),
        ],
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
        fallbacks=[
            CommandHandler('cancel', cancel_admin_lesson),
            CommandHandler('start', cancel_admin_lesson),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_admin_lesson),
        ],
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
            CommandHandler('start', broadcast_cancel),
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, broadcast_cancel),
        ],
    )

    # Додаємо діалоги в диспетчер
    application.add_handler(registration_conv)
    application.add_handler(add_lesson_conv)
    application.add_handler(create_group_conv)
    application.add_handler(admin_lesson_conv)
    application.add_handler(broadcast_conv)

    # ==========================================
    # 4. КНОПКИ МЕНЮ ТА ЗАВЕРШЕННЯ ЧАТУ
    # ==========================================
    # Кнопка завершення активного діалогу (працює завжди)
    application.add_handler(MessageHandler(filters.Regex(r'^Завершити діалог'), chat_end))

    # ЄДИНИЙ маршрутизатор кнопок головного меню.
    # Він тихо закриває активний чат і викликає потрібну функцію.
    # ('➕ Додати урок' та '📢 Масова розсилка' перехоплюються conv-хендлерами вище.)
    application.add_handler(MessageHandler(MAIN_MENU_BUTTONS_FILTER, menu_button_router))

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
    # 6. ІНЛАЙН РОУТЕРИ
    # ВАЖЛИВО: порядок має значення — специфічні патерни ВИЩЕ загальних!
    # ==========================================
    # Швидкі відповіді (старт чату по кнопці під повідомленням)
    application.add_handler(CallbackQueryHandler(teacher_quick_reply_start, pattern=r'^inbox_reply_\d+$'))
    application.add_handler(CallbackQueryHandler(quick_reply_start, pattern=r'^quick_reply_(teacher|group)_\d+$'))

    application.add_handler(CallbackQueryHandler(show_media_gallery, pattern=r'^show_media_gallery_\d+$'))
    application.add_handler(CallbackQueryHandler(chat_engine_callbacks, pattern=r'^chat_page_'))
    application.add_handler(CallbackQueryHandler(chat_engine_callbacks, pattern=r'^export_chat_current$'))
    # Загальний роутер чатів — один раз (без дублікату)
    application.add_handler(CallbackQueryHandler(chat_engine_callbacks, pattern=r'.*chat.*'))

    application.add_handler(
        CallbackQueryHandler(student_callbacks, pattern='^(student_schedule|back_student_schedule)'))

    application.add_handler(
        CallbackQueryHandler(teacher_callbacks, pattern='^(inbox|schedule|back_schedule|back_to_schedule)'))

    application.add_handler(CallbackQueryHandler(
        admin_callbacks,
        pattern='^(admin|show|toggle|confirm|list|edit|change|assign|add|remove|manage|back_admin|back_groups|group_type|select_group|select_teacher|assign_to_student|student_page|finish_create|cancel_create)'
    ))

    # Спільні callback-и (календар, back_to_menu, ignore)
    application.add_handler(CallbackQueryHandler(common_callbacks,
                                                 pattern='^(ignore|back_to_menu|cal_|back_to_calendar_)'))

    # ==========================================
    # 7. ГЛОБАЛЬНІ ОБРОБНИКИ ТЕКСТУ ТА МЕДІА
    # (сюди потрапляють повідомлення активних чатів — миттєве пересилання)
    # ==========================================
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_message_handler))
    application.add_handler(MessageHandler(MEDIA_FILTER, global_media_handler))

    print("🚀 Бот запущено...")
    print(f"👑 Головний адміністратор: ID {SUPER_ADMIN_ID}")
    print("📅 Автоматичні нагадування про уроки налаштовані на 8:00")

    application.run_polling()


if __name__ == '__main__':
    main()
