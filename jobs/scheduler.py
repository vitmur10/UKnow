import sqlite3
from datetime import datetime, time

import pytz
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import SUPER_ADMIN_ID
from database.db_manager import db
from utils.helpers import format_lesson_time


async def send_daily_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет ежедневные напоминания об уроках в 8:00 по киевскому времени"""
    kiev_tz = pytz.timezone('Europe/Kiev')

    # ВОТ ЭТО МЫ ДОБАВИЛИ, ЧТОБЫ ПРИНТ НИЖЕ ЗАРАБОТАЛ:
    now = datetime.now(kiev_tz)

    today = now.date()

    print(f"--- ДИАГНОСТИКА РАССЫЛКИ ---")
    print(f"🔔 Текущее время в боте (Киев): {now.strftime('%H:%M:%S')}")

    # Готовим два формата даты
    date_iso = today.strftime('%Y-%m-%d')  # 2026-02-28
    date_ukr = today.strftime('%d.%m.%Y')  # 28.02.2026

    print(f"🔎 Ищем уроки на: {date_iso} или {date_ukr}")

    conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
    cursor = conn.cursor()

    # Ищем уроки, которые подходят под любой из двух форматов даты
    cursor.execute('''SELECT l.id, l.teacher_id, l.student_id, l.group_id, l.lesson_date, l.lesson_time,
                             t.first_name, t.last_name, s.first_name, s.last_name, g.name
                      FROM lessons l
                      LEFT JOIN users t ON l.teacher_id = t.user_id
                      LEFT JOIN users s ON l.student_id = s.user_id
                      LEFT JOIN groups g ON l.group_id = g.id
                      WHERE (l.lesson_date = ? OR l.lesson_date = ?) 
                      AND (l.status = 'scheduled' OR l.status = 'Scheduled')''',
                   (date_iso, date_ukr))

    lessons_today = cursor.fetchall()
    conn.close()

    if not lessons_today:
        print(f"📅 На {today} запланированных уроков в базе не найдено.")
        return

    print(f"📚 Найдено {len(lessons_today)} уроков. Начинаю отправку...")

    sent_count = 0

    for lesson in lessons_today:
        lesson_id = lesson[0]  # id
        teacher_id = lesson[1]  # teacher_id (user_id викладача)
        student_id = lesson[2]  # student_id (user_id студента или None)
        group_id = lesson[3]  # group_id
        lesson_date = lesson[4]  # lesson_date
        lesson_time = lesson[5]  # lesson_time
        teacher_first = lesson[6]  # teacher first name
        teacher_last = lesson[7]  # teacher last name
        student_first = lesson[8]  # student first name
        student_last = lesson[9]  # student last name
        group_name = lesson[10]  # group name

        print(f"📋 Урок ID {lesson_id}: викладач {teacher_id}, студент {student_id}, група {group_id}")

        # Проверяем что ID валидные (числа)
        def is_valid_user_id(user_id):
            try:
                return user_id and isinstance(user_id, int) and user_id > 0
            except:
                return False

        # Форматируем время для сообщения
        formatted_time = format_lesson_time(lesson_time) if lesson_time else "Не вказано"

        # Форматируем сообщение
        reminder_text = (
            f"Доброго дня! 😊\n\n"
            f"Нагадуємо, що ваш урок відбудеться {lesson_date} о {formatted_time} за українським часом.\n\n"
            f"📚Будь ласка, підготуйте все необхідне для заняття. Якщо у вас виникнуть запитання чи зміни, зв’яжіться з нами заздалегідь.\n\n"
            f"📌За правилами нашого освітнього центру, просимо попереджати про відміну заняття завчасно — щонайменше за 2 години.\n"
            f"Якщо цього не зробити, заняття, на жаль, вважається проведеним.\n"
            f"У разі запізнення урок триває протягом залишку запланованого часу.\n\n"
            f"Гарного дня! 🌟"
        )

        # Отправляем преподавателю
        if is_valid_user_id(teacher_id):
            try:
                await context.bot.send_message(teacher_id, reminder_text)
                sent_count += 1
                print(f"✅ Напоминание отправлено преподавателю {teacher_id} ({teacher_first} {teacher_last})")
            except Exception as e:
                print(f"❌ Ошибка отправки напоминания преподавателю {teacher_id}: {e}")
        else:
            print(f"⚠️ Неправильный ID преподавателя: {teacher_id}")

        # Отправляем студенту (для индивидуальных уроков)
        if is_valid_user_id(student_id):
            try:
                await context.bot.send_message(student_id, reminder_text)
                sent_count += 1
                print(f"✅ Напоминание отправлено студенту {student_id} ({student_first} {student_last})")
            except Exception as e:
                print(f"❌ Ошибка отправки напоминания студенту {student_id}: {e}")

        # Отправляем участникам группы (для групповых уроков)
        if group_id and not student_id:  # групповой урок
            print(f"📤 Отправка напоминаний участникам группы {group_id} ({group_name})")
            group_members = db.get_group_members(group_id)
            for member in group_members:
                member_id = member[0]
                if is_valid_user_id(member_id):
                    try:
                        await context.bot.send_message(member_id, reminder_text)
                        sent_count += 1
                        print(f"✅ Напоминание отправлено участнику группы {member_id} ({member[2]} {member[3]})")
                    except Exception as e:
                        print(f"❌ Ошибка отправки напоминания участнику группы {member_id}: {e}")
                else:
                    print(f"⚠️ Неправильный ID участника группы: {member_id}")

    print(f"📊 Всего отправлено напоминаний: {sent_count}")


def schedule_daily_reminders(application):
    """Настраивает ежедневные напоминания на 8:00 по киевскому времени"""
    job_queue = application.job_queue

    # Устанавливаем киевский часовой пояс
    kiev_tz = pytz.timezone('Europe/Kiev')

    # Запускаем сегодня в 21:22
    job_queue.run_daily(
        send_daily_reminders,
        time=time(hour=8, minute=0, tzinfo=kiev_tz),
        name='daily_lesson_reminders'
    )

    print("📅 Автоматические напоминания настроены на 8:00 по киевскому времени")


async def force_test_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для мгновенного запуска рассылки (только для админа)"""
    if update.effective_user.id != SUPER_ADMIN_ID:
        return
    await update.message.reply_text("🚀 Запускаю рассылку вручную...")
    await send_daily_reminders(context)
    await update.message.reply_text("🏁 Ручной запуск завершен. Проверь консоль!")


async def test_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестирования напоминаний (только для главного админа)"""
    user_id = update.effective_user.id

    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Только главный администратор может тестировать напоминания.")
        return

    await update.message.reply_text("🔄 Запускаю тестовые напоминания...")

    try:
        await send_daily_reminders(context)
        await update.message.reply_text("✅ Тестовые напоминания отправлены!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при отправке напоминаний: {str(e)}")