def get_main_keyboard(role):
    if role == 'student':
        keyboard = [
            [KeyboardButton("💬 Написати викладачеві/групі"), KeyboardButton("🗓 Мій календар")],
            [KeyboardButton("🏫 Про школу"), KeyboardButton("📋 Правила школи")],
            [KeyboardButton("❓ Популярні питання"), KeyboardButton("📞 Написати менеджеру")],
            [KeyboardButton("📖 Історія переписок")]
        ]
    elif role == 'teacher':
        keyboard = [
            [KeyboardButton("📬 Вхідні"), KeyboardButton("💬 Написати учневі/групі")],
            [KeyboardButton("👨‍🎓 Мої учні"), KeyboardButton("📚 Мої групи")],
            [KeyboardButton("📆 Мій розклад"), KeyboardButton("➕ Додати урок")],
            [KeyboardButton("📊 Статистика"), KeyboardButton("📞 Написати менеджеру")],
            [KeyboardButton("📖 Історія переписок")]
        ]
    else:  # admin
        keyboard = [
            [KeyboardButton("👨‍💼 Керування користувачами")],
            [KeyboardButton("👥 Керування групами")],
            [KeyboardButton("🗓 Керування розкладом")],
            [KeyboardButton("🗂️ Переписки / Чати")],
            [KeyboardButton("📢 Масова розсилка"), KeyboardButton("📊 Звіти")]
        ]

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_language_keyboard():
    keyboard = []
    for i in range(0, len(LANGUAGES), 2):
        row = [InlineKeyboardButton(LANGUAGES[i], callback_data=f"lang_{i}")]
        if i + 1 < len(LANGUAGES):
            row.append(InlineKeyboardButton(LANGUAGES[i + 1], callback_data=f"lang_{i+1}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def get_chat_active_keyboard():
    """Возвращает клавиатуру для активного диалога."""
    keyboard = [
        [KeyboardButton("Завершити діалог 🔚")]
    ]
    # Используем ReplyKeyboardMarkup, чтобы кнопка была видна под полем ввода
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_broadcast_target_keyboard():
    """Повертає клавіатуру для вибору цілі розсилки (спрощений варіант)."""
    keyboard = [
        # УЧНІ
        [InlineKeyboardButton("🎓 Учні: ВСІ", callback_data="bc_target_students_all")],

        # ВИКЛАДАЧІ
        [InlineKeyboardButton("👨‍🏫 Викладачі: ВСІ", callback_data="bc_target_teachers_all")],

        [InlineKeyboardButton("❌ Скасувати розсилку", callback_data="cancel_broadcast")]
    ]
    return InlineKeyboardMarkup(keyboard)