from datetime import datetime


def is_lesson_link(text):
    """Перевіряє, чи є текст запрошенням на відеоурок (Zoom/Meet/Teams)."""
    if not text:
        return False

    text_lower = text.lower()

    # Список доменів сервісів відеозв'язку
    lesson_domains = ['zoom.us', 'meet.google.com', 'teams.live.com', 'teams.microsoft.com']

    # Перевіряємо, чи є хоча б один домен у тексті
    has_domain = any(domain in text_lower for domain in lesson_domains)

    # Ключові слова для контексту
    keywords = ['конференция', 'подключиться', 'идентификатор', 'код доступа',
                'зустріч', 'вхід на урок', 'приєднуйтесь']
    has_keywords = any(word in text_lower for word in keywords)

    # Повертаємо True, якщо знайшли домен АБО якщо є будь-яке посилання + ключове слово
    if has_domain:
        return True
    if 'http' in text_lower and has_keywords:
        return True

    return False


def format_lesson_time(lesson_time_str):
    """Форматирует время урока из строки HH:MM:SS в HH:MM"""
    try:
        if lesson_time_str:
            # Если время в формате HH:MM:SS, обрезаем секунды
            if len(lesson_time_str.split(':')) == 3:
                return ':'.join(lesson_time_str.split(':')[:2])
            else:
                return lesson_time_str
        return "Не вказано"
    except:
        return "Не вказано"


def format_lesson_date_time(date_str, time_str):
    """Конвертує дату (YYYY-MM-DD) та час (HH:MM:SS) у потрібний формат."""

    # 1. Форматування Дати: '2025-11-28' -> '28.11.2025'
    try:
        # Використовуємо datetime.strptime для розбору рядка дати
        date_obj = datetime.strptime(str(date_str), '%Y-%m-%d').date()
        formatted_date = date_obj.strftime('%d.%m.%Y')
    except (ValueError, TypeError):
        formatted_date = str(date_str)  # Якщо помилка, повертаємо як є

    # 2. Форматування Часу: '10:00:00' -> '10:00 по Києву'
    try:
        # Використовуємо datetime.strptime для розбору рядка часу
        time_obj = datetime.strptime(str(time_str), '%H:%M:%S').time()
        formatted_time = time_obj.strftime('%H:%M')
        formatted_time_with_tz = f"{formatted_time} по Києву"
    except (ValueError, TypeError):
        formatted_time_with_tz = f"{str(time_str)} по Києву"  # Якщо помилка, повертаємо як є

    return formatted_date, formatted_time_with_tz


def get_broadcast_users(target_data, db):
    """Визначає список ID користувачів на основі обраної цілі (Учні ВСІ або Викладачі ВСІ)."""

    users = []

    if target_data == 'bc_target_students_all':
        # Використовуємо метод, який має бути у вашому класі Database
        users = db.get_users_by_role('student')

    elif target_data == 'bc_target_teachers_all':
        users = db.get_users_by_role('teacher')

    # users: [ (id, tg_id, first_name, last_name, role, lang, ...) ]
    # Повертаємо тільки user_id
    return [u[0] for u in users]
