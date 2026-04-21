import calendar
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from config.settings import LANGUAGES
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


def get_calendar_keyboard(year, month):
    """Генерує інлайн-клавіатуру з календарем на обраний місяць та рік."""
    keyboard = []

    # 1. Перший ряд - Місяць і Рік
    month_names = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
                   "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
    keyboard.append([InlineKeyboardButton(f"{month_names[month - 1]} {year}", callback_data="ignore")])

    # 2. Другий ряд - дні тижня
    week_days = ["Пн", "Вв", "Ср", "Чт", "Пт", "Сб", "Нд"]
    row = [InlineKeyboardButton(day, callback_data="ignore") for day in week_days]
    keyboard.append(row)

    # 3. Дні місяця
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"cal_date_{year}_{month}_{day}"))
        keyboard.append(row)

    # 4. Навігація (Попередній / Сьогодні / Наступний)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.append([
        InlineKeyboardButton("⬅️", callback_data=f"cal_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton("Сьогодні", callback_data="cal_today"),
        InlineKeyboardButton("➡️", callback_data=f"cal_next_{next_year}_{next_month}")
    ])

    return InlineKeyboardMarkup(keyboard)