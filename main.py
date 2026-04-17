from multiprocessing import context
from pyexpat.errors import messages

from telegram import Update
from telegram.ext import CallbackContext

import shutil 
import os

import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional
import requests
import json
import re
import calendar
import pytz


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from telegram.constants import ParseMode
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = ""

MESSAGES_PER_PAGE = 20
#Смотреть картинку
IMAGE_WARNING_FILE_ID = "AgACAgIAAxkBAANnaT19FCc1xzRo7jpVDg-Z1xLD9LkAAqYLaxuyKPFJTpOEh7vOf9QBAAMCAAN5AAM2BA"

# --------------------------
# БУФЕР МЕДІА-ГРУП (альбомів)
# --------------------------



# Conversation states
REGISTER_NAME, REGISTER_LANG, REGISTER_BIRTHDATE, REGISTER_PHONE = range(4)
ADD_LESSON_STUDENT, ADD_LESSON_DATE, ADD_LESSON_TIME = range(4, 7)
ADMIN_ASSIGN, ADMIN_MESSAGE = range(7, 9)
CREATE_GROUP_NAME, CREATE_GROUP_TYPE, CREATE_GROUP_TEACHER, CREATE_GROUP_STUDENTS = range(9, 13)
TEACHER_MESSAGE_SELECT, TEACHER_MESSAGE_TEXT, TEACHER_CHAT_ACTIVE = range(13, 16)
CHAT_HISTORY_SELECT, CHAT_HISTORY_DATE = range(15, 17)
ADMIN_SELECT_USER, ADMIN_ADD_LESSON_DATE, ADMIN_ADD_LESSON_TIME = range(17, 20)
LESSON = range(20, 21)
STUDENT_MESSAGE_SELECT = 16 
STUDENT_CHAT_ACTIVE = 17
BROADCAST_SELECT_TARGET, BROADCAST_WAIT_MESSAGE, BROADCAST_SELECT_LIST = range(24, 27)



ALL_MAIN_MENU_BUTTONS_LIST = [
    # Кнопки УЧЕНИКА
    "💬 Написати викладачеві/групі", "🗓 Мій календар", 
    "🏫 Про школу", "📋 Правила школи", "❓ Популярні питання", 
    "📞 Написати менеджеру", "📖 Історія переписок",
    
    # Кнопки ПРЕПОДАВАТЕЛЯ
    "📬 Вхідні", "👨‍🎓 Мої учні", "📚 Мої групи", "📆 Мій розклад", 
    "💬 Написати учневі/групі", "➕ Додати урок", "📊 Статистика",
    
    # Кнопки АДМИНИСТРАТОРА
    "👨‍💼 Керування користувачами", "👥 Керування групами", 
    "🗓 Керування розкладом", "🗂️ Переписки / Чати", 
    "📢 Масова розсилка", "📊 Звіти"
]

MAIN_MENU_BUTTONS_FILTER = filters.Text(ALL_MAIN_MENU_BUTTONS_LIST)

TRIGGER_WORDS = ["допомога", "скарга", "проблема", "конфлікт", "не влаштовує"]

# Language options
LANGUAGES = [
    "🇺🇸 Англійська", "🇩🇪 Німецька", "🇨🇿 Чеська", "🇮🇹 Італійська",
    "🇪🇸 Іспанська", "🇵🇱 Польська", "🇸🇰 Словацька", "🇫🇷 Французька"
]

SUPER_ADMIN_ID = 


# --------------------------
# НАЛАШТУВАННЯ БАЗИ ДАНИХ ТА BACKUP
# --------------------------
DB_NAME = 'school_bot.db' # Назва, яку ми підтвердили!
BACKUP_DIR = 'backups' 

# --------------------------
# ФУНКЦІЯ ДЛЯ РЕЗЕРВНОГО КОПІЮВАННЯ (одразу після констант)
# --------------------------
async def create_backup(db_name: str, backup_dir: str):
    """Створює резервну копію бази даних і повертає шлях до файлу."""
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir) # Це на всяк випадок

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}_{db_name}"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        shutil.copyfile(db_name, backup_path)
        return backup_path
    except Exception as e:
        print(f"Помилка створення резервної копії: {e}")
        return None







# НОВЕ ПОСИЛАННЯ (Версія 11)
GOOGLE_SCRIPT_URL = ""





# application.add_handler(CommandHandler("test_gs", test_gs))















async def debug_student_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Функция для отладки - показывает все уроки студента"""
    user_id = update.effective_user.id
    lessons = db.get_student_lessons(user_id)
    
    if not lessons:
        await update.message.reply_text("DEBUG: У вас нет уроков в базе данных")
    else:
        text = f"DEBUG: Найдено {len(lessons)} уроков:\n\n"
        for i, lesson in enumerate(lessons, 1):
            text += f"{i}. Дата: {lesson[3]}, Время: {lesson[4]}\n"
            text += f"   Викладач: {lesson[6]} {lesson[7]}\n"
            if lesson[2]:  # student_id
                text += "   Тип: Індивідуальний\n"
            else:  # group
                text += f"   Тип: Група {lesson[8] or 'Невідомо'}\n"
            text += "\n"
        
        # Отправляем по частям если текст слишком длинный
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(text)




async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await debug_student_lessons(update, context)




async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    user = db.get_user(user_id)
    
    # Ігнорувати неактивні кнопки
    if data == "ignore":
        return

    # --- 📬 ВХІДНІ (INBOX) ---
    if data.startswith("inbox_open_"):
        student_id = int(data.split("_")[2])
        await teacher_inbox_open(query, context, student_id)
        return

    if data == "inbox_back":
        # Повернення до списку вхідніх
        teacher_id = query.from_user.id
        unread_list = db.get_unread_count_per_student(teacher_id)
        if not unread_list:
            await query.edit_message_text("📭 Нових повідомлень немає.")
            return
        keyboard = []
        for sid, fn, ln, count, last_time, last_msg in unread_list:
            preview = (last_msg or "")[:30].replace("\n", " ")
            if len(last_msg or "") > 30:
                preview += "…"
            keyboard.append([InlineKeyboardButton(
                f"🔴 {fn} {ln}  [{count} нових]  {preview}",
                callback_data=f"inbox_open_{sid}"
            )])
        total = sum(r[3] for r in unread_list)
        await query.edit_message_text(
            f"📬 <b>Вхідні</b> — {total} нових повідомлень\n\nОберіть учня:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return
    
    # Головне меню
    if data == "back_to_menu":
        role = user[4] if user else 'student'
        await query.edit_message_text("Головне меню:")
        await query.message.reply_text("Оберіть дію:", reply_markup=get_main_keyboard(role))
        return
    
    # Мови при реєстрації
    if data.startswith("lang_"):
        await register_language(update, context)
        return REGISTER_BIRTHDATE
    
# --- РОЗКЛАД УЧНЯ (Мульти-вибір з ПРІНТАМИ) ---
    if data.startswith("admin_cancel_student_") or data.startswith("toggle_multi_"):
        print(f"\n[DEBUG] Вхід в блок скасування. Data: {data}")
        
        parts = data.split("_")
        
        # Визначаємо ID учня залежно від того, як ми сюди потрапили
        if data.startswith("toggle_multi_"):
            # Формат: toggle_multi_LESSONID_STUDENTID_SELECTEDIDS
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
            # Формат: admin_cancel_student_STUDENTID
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
            
            # --- НОВА КОРЕКЦІЯ ІНДЕКСІВ (згідно з фото) ---
            # Судячи з того, що на місці часу з'явився рік "2026-", 
            # а на місці дати "??.??", спробуємо змістити індекси:
            
            l_date = lesson[4] if len(lesson) > 4 else "??.??" # Спробуємо 4 для дати
            l_time = lesson[5][:5] if len(lesson) > 5 and lesson[5] else "??:??" # Спробуємо 5 для часу
            
            # Викладач
            # На фото ми бачимо "60 scheduled". Це означає, що lesson[6] = 60, lesson[7] = scheduled
            # А ім'я викладача має бути далі. Спробуємо взяти 9 та 10 індекси.
            t_first = lesson[9] if len(lesson) > 9 and lesson[9] else ""
            t_last = lesson[10] if len(lesson) > 10 and lesson[10] else ""
            t_name = f"{t_first} {t_last}".strip() or f"Викл (ID: {lesson[6]})"
            # ----------------------------------------------

            if lesson[2]:  # Індивідуальний
                lesson_text = f"{mark}📚 {l_date} о {l_time} — викл: {t_name}"
            else:  # Груповий
                g_name = lesson[13] if len(lesson) > 13 and lesson[13] else "Група"
                lesson_text = f"{mark}👥 {l_date} о {l_time} — гр: {g_name}"
            
            keyboard.append([InlineKeyboardButton(
                lesson_text,
                callback_data=f"toggle_multi_{lesson_id}_{student_id}_{selected_str}"
            )])
        
        # Кнопка скасування
        if selected_ids:
            final_callback = f"confirm_multi_cancel_{student_id}_{selected_str}"
            print(f"[DEBUG] Генеруємо кнопку скасування. Callback: {final_callback}")
            print(f"[DEBUG] Довжина callback: {len(final_callback)} символів (ліміт 64!)")
            
            keyboard.append([InlineKeyboardButton(
                f"🔥 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})", 
                callback_data=final_callback
            )])

        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_student_{student_id}")])
        
        text = f"🗑 **Мульти-скасування для {student[2]} {student[3]}**\n\n"
        text += "Оберіть уроки (натисніть ще раз, щоб зняти вибір):"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        print("[DEBUG] Повідомлення оновлено, чекаємо наступного кліку...")
        return

    # ... інший код обробки кнопок ...

    # Обробка кнопок фільтрів користувачів
    if data == "list_by_students":
        await send_full_user_list(update, context, role='student')
        return

    if data == "list_by_teachers":
        await send_full_user_list(update, context, role='teacher')
        return

    if data == "list_all_users":
        await send_full_user_list(update, context)
        return

    # Обробка кнопки "Назад" з меню списку користувачів
    if data == "back_to_admin_users":
        await show_user_filters_menu(update.callback_query, context)
        return

    # ... інший код обробки кнопок ...
    if data == "list_users": # ПОВЕРНІТЬ СТАРУ НАЗВУ!
        await show_user_filters_menu(query, context)
        return

    # Обробка кнопок фільтрів користувачів
    if data == "list_by_students":
        await send_full_user_list(update, context, role='student')
        return

# Скасування уроків викладача (Мульти-вибір)
    if data.startswith("admin_cancel_teacher_") or data.startswith("toggle_teacher_"):
        parts = data.split("_")
        
        # Визначаємо ID викладача
        # Якщо це перший вхід (admin_cancel_teacher_ID) - індекс 3
        # Якщо це перемикання (toggle_teacher_LESSONID_TEACHERID_...) - індекс 3
        if data.startswith("toggle_teacher_"):
            teacher_id = int(parts[3])
            clicked_lesson_id = parts[2]
            selected_ids = parts[4].split(":") if len(parts) > 4 and parts[4] else []
            
            # Додаємо/видаляємо урок зі списку
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
            
            if lesson[2]:  # індивідуально
                lesson_text = f"{mark}📚 {lesson[3]} {lesson[4]} - уч: {lesson[6]} {lesson[7]}"
            else:  # група
                lesson_text = f"{mark}👥 {lesson[3]} {lesson[4]} - гр: {lesson[8] or 'Невідомо'}"
            
            # Кнопка для кожного уроку
            keyboard.append([InlineKeyboardButton(
                lesson_text,
                callback_data=f"toggle_teacher_{l_id}_{teacher_id}_{selected_str}"
            )])
        
        # Якщо вибрано хоча б один урок — додаємо кнопку дії
        if selected_ids:
            keyboard.append([InlineKeyboardButton(
                f"🗑 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})", 
                callback_data=f"confirm_multi_teacher_{teacher_id}_{selected_str}"
            )])

        # Кнопка повернення
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_teacher_{teacher_id}")])
        
        await query.edit_message_text(
            f"🗑 **Скасування уроків викладача {teacher[2]} {teacher[3]}**\n\n"
            f"Оберіть уроки (вибрано: {len(selected_ids)}):",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

# Скасування уроків групи (Мульти-вибір)
    if data.startswith("admin_cancel_group_") or data.startswith("toggle_group_"):
        parts = data.split("_")
        
        # Визначаємо ID групи та вибрані уроки
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

        # Отримуємо дані групи та уроки
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
            
            # ВИПРАВЛЕНІ ІНДЕКСИ:
            l_date = lesson[4] # Дата
            l_time = lesson[5][:5] if lesson[5] else "--:--" # Час (перші 5 символів)
            t_fname = lesson[8] if len(lesson) > 8 else "" # Ім'я викладача
            t_lname = lesson[9] if len(lesson) > 9 else "" # Прізвище викладача
            
            # Формуємо текст кнопки: [✅] 📚 16.03.2026 13:00 - викл: Прізвище
            lesson_text = f"{mark}📚 {l_date} {l_time} - викл: {t_lname}"
            
            keyboard.append([InlineKeyboardButton(
                lesson_text,
                callback_data=f"toggle_group_{l_id}_{group_id}_{selected_str}"
            )])
        
        # Кнопка для видалення всіх вибраних
        if selected_ids:
            # Зберігаємо список в пам'ять, щоб не перевантажувати кнопку
            context.user_data['pending_termination_ids'] = selected_ids
            
            keyboard.append([InlineKeyboardButton(
                f"🗑 СКАСУВАТИ ВИБРАНІ ({len(selected_ids)})", 
                callback_data=f"confirm_multi_group_{group_id}" # ID уроків тут більше не пишемо
            )])

        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_group_{group_id}")])
        
        group_name = group[1] if group else 'Невідомо'
        await query.edit_message_text(
            f"🗑 **Скасування уроків групи {group_name}**\n\n"
            f"Оберіть уроки для видалення:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # ФІЗИЧНЕ ВИДАЛЕННЯ ТА НОВИЙ ФОРМАТ СПОВІЩЕНЬ
    if data.startswith("confirm_multi_group_"):
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

        lessons_to_notify = [] # Список для деталей уроків
        success_count = 0

        for l_id in selected_ids:
            if not l_id: continue
            try:
                # Отримуємо дату і час перед видаленням
                conn = sqlite3.connect(db.db_name)
                cursor = conn.cursor()
                cursor.execute("SELECT lesson_date, lesson_time FROM lessons WHERE id = ?", (int(l_id),))
                info = cursor.fetchone()
                conn.close()

                if info:
                    # Форматуємо дату (напр. 16.03.2026) та час (13:00)
                    date_str = datetime.strptime(info[0], '%Y-%m-%d').strftime('%d.%m.%Y')
                    time_str = info[1][:5]
                    lessons_to_notify.append(f"📅 {date_str} о {time_str} (за Києвом)")

                # Скасовуємо
                db.cancel_lesson(int(l_id)) 
                success_count += 1
            except Exception as e:
                logger.error(f"Помилка при скасуванні {l_id}: {e}")

        if success_count > 0:
            # Створюємо список скасованих занять для повідомлення
            lessons_list = "\n".join(lessons_to_notify)
            
            # ФОРМАТ ПОВІДОМЛЕННЯ ДЛЯ УЧНІВ ТА ВИКЛАДАЧА
            notification_text = (
                f"❌ **Урок скасовано адміністрацією**\n"
                f"{lessons_list}\n"
                f"👥 Група: **{group_name}**"
            )

            # Розсилка учням
            for member in members:
                try:
                    await context.bot.send_message(
                        chat_id=member[0], 
                        text=notification_text, 
                        parse_mode="Markdown"
                    )
                except: continue

            # Розсилка викладачу
            if teacher_id:
                try:
                    await context.bot.send_message(
                        chat_id=teacher_id, 
                        text=notification_text, # Використовуємо той самий формат
                        parse_mode="Markdown"
                    )
                except: pass

        # Очищення та звіт адміну
        context.user_data['pending_termination_ids'] = []
        await query.edit_message_text(
            f"✅ Успішно скасовано {success_count} уроків. Повідомлення надіслано.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_group_{group_id}")]])
        )
        return

    if data.startswith("change_student_teacher"):
        # Визначаємо сторінку
        page = int(data.split("_")[3]) if len(data.split("_")) > 3 else 0
        items_per_page = 10
        
        students = db.get_users_by_role('student')
        if not students:
            await query.edit_message_text("Немає студентів.")
            return
        
        total_pages = (len(students) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        current_students = students[start_idx : start_idx + items_per_page]

        keyboard = []
        for student in current_students:
            teacher = db.get_student_teacher(student[0])
            teacher_info = f" (викл: {teacher[2]} {teacher[3]})" if teacher else " (без викладача)"
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 {student[2]} {student[3]}{teacher_info}",
                callback_data=f"change_teacher_for_student_{student[0]}"
            )])

        # Кнопки навігації
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"change_student_teacher_{page - 1}"))
        
        nav_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
        
        if (start_idx + items_per_page) < len(students):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"change_student_teacher_{page + 1}"))
        
        keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"🔄 Зміна викладача учня\n\nОберіть учня (сторінка {page + 1}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "student_schedule_today":
        today = datetime.now().date()
        lessons = db.get_student_lessons(user_id, today)
        
        if not lessons:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n❌ Уроків немає"
        else:
            text = f"📅 Мій календар на сьогодні ({today.strftime('%d.%m.%Y')})\n\n"
            for lesson in lessons:
                lesson_time = format_lesson_time(lesson[5])  # lesson_time это индекс 5
                teacher_name = f"{lesson[9]} {lesson[10]}" if lesson[9] and lesson[10] else "Невідомо"  # индексы 9,10
                
                # Определяем тип урока
                if lesson[2]:  # индивидуальный урок
                    lesson_type = "індивідуально"
                else:  # групповой урок
                    group_name = lesson[11] if lesson[11] else "Невідомо"  # group_name это индекс 11
                    lesson_type = f"група {group_name}"
                
                text += f"📚 Час: {lesson_time}\n"
                text += f"    👨‍🏫 Викладач: {teacher_name}\n"
                text += f"    📋 Тип: {lesson_type}\n\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Выбор нового преподавателя для студента
    if data.startswith("change_teacher_for_student_"):
        parts = data.split("_")
        student_id = int(parts[4])
        # Додаємо підтримку сторінок для вчителів (елемент індексу 5, якщо є)
        page = int(parts[5]) if len(parts) > 5 else 0
        items_per_page = 10

        student = db.get_user(student_id)
        current_teacher = db.get_student_teacher(student_id)
        
        teachers = db.get_users_by_role('teacher')
        if not teachers:
            await query.edit_message_text("Немає викладачів для призначення.")
            return
        
        available_teachers = [t for t in teachers if not current_teacher or t[0] != current_teacher[0]]
        
        total_pages = (len(available_teachers) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        current_list = available_teachers[start_idx : start_idx + items_per_page]

        keyboard = []
        if current_teacher and page == 0: # Показуємо кнопку видалення тільки на 1-й сторінці
            keyboard.append([InlineKeyboardButton(
                "❌ Прибрати викладача (залишити без викладача)",
                callback_data=f"remove_teacher_from_student_{student_id}"
            )])
        
        for teacher in current_list:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🏫 {teacher[2]} {teacher[3]}",
                callback_data=f"assign_new_teacher_{student_id}_{teacher[0]}"
            )])

        # Навігація для списку вчителів
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"change_teacher_for_student_{student_id}_{page - 1}"))
        
        nav_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
        
        if (start_idx + items_per_page) < len(available_teachers):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"change_teacher_for_student_{student_id}_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("⬅️ До вибору учня", callback_data="change_student_teacher")])
        
        current_teacher_text = f"Поточний викладач: {current_teacher[2]} {current_teacher[3]}" if current_teacher else "Поточний викладач: відсутній"
        
        await query.edit_message_text(
            f"🔄 Зміна викладача для {student[2]} {student[3]}\n\n"
            f"{current_teacher_text}\n\n"
            f"Оберіть нового викладача (сторінка {page + 1}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Назначить нового преподавателя
    if data.startswith("assign_new_teacher_"):
        parts = data.split("_")
        student_id = int(parts[3])
        new_teacher_id = int(parts[4])
        
        student = db.get_user(student_id)
        old_teacher = db.get_student_teacher(student_id)
        new_teacher = db.get_user(new_teacher_id)
        
        try:
            # Назначить нового преподавателя
            db.assign_teacher_to_student(new_teacher_id, student_id)
            
            success_text = (f"✅ Викладач успішно змінений!\n\n"
                        f"👨‍🎓 Студент: {student[2]} {student[3]}\n")
            
            if old_teacher:
                success_text += f"👨‍🏫 Старий викладач: {old_teacher[2]} {old_teacher[3]}\n"
            else:
                success_text += f"👨‍🏫 Старий викладач: відсутній\n"
            
            success_text += f"👨‍🏫 Новий викладач: {new_teacher[2]} {new_teacher[3]}"
            
            await query.edit_message_text(success_text)
            
            # Уведомить старого преподавателя
            if old_teacher:
                try:
                    await context.bot.send_message(
                        old_teacher[0],
                        f"📢 Зміна призначення\n\n"
                        f"Студент {student[2]} {student[3]} більше не є вашим учнем.\n"
                        f"Новий викладач: {new_teacher[2]} {new_teacher[3]}"
                    )
                except:
                    pass
            
            # Уведомить нового преподавателя
            try:
                await context.bot.send_message(
                    new_teacher_id,
                    f"👨‍🎓 Новий учень!\n\n"
                    f"Вам призначено студента: {student[2]} {student[3]}\n"
                    f"{'Попередній викладач: ' + old_teacher[2] + ' ' + old_teacher[3] if old_teacher else 'Раніше студент був без викладача'}"
                )
            except:
                pass
            
            # Уведомить студента
            try:
                await context.bot.send_message(
                    student_id,
                    f"👨‍🏫 Зміна викладача\n\n"
                    f"{'Ваш попередній викладач: ' + old_teacher[2] + ' ' + old_teacher[3] if old_teacher else 'Раніше ви були без викладача'}\n"
                    f"Ваш новий викладач: {new_teacher[2]} {new_teacher[3]}\n\n"
                    f"Незабаром з вами зв'яжеться новий викладач!"
                )
            except:
                pass
                
        except Exception as e:
            await query.edit_message_text(f"❌ Помилка зміни викладача: {str(e)}")
        return

    # Убрать преподавателя у студента
    if data.startswith("remove_teacher_from_student_"):
        student_id = int(data.split("_")[4])
        student = db.get_user(student_id)
        old_teacher = db.get_student_teacher(student_id)
        
        if not old_teacher:
            await query.edit_message_text("❌ У студента вже немає призначеного викладача.")
            return
        
        try:
            # Убрать преподавателя (деактивировать назначение)
            conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE assignments SET is_active = 0 WHERE student_id = ?", (student_id,))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ Викладач прибраний!\n\n"
                f"👨‍🎓 Студент: {student[2]} {student[3]}\n"
                f"👨‍🏫 Прибраний викладач: {old_teacher[2]} {old_teacher[3]}\n\n"
                f"Студент тепер без призначеного викладача."
            )
            
            # Уведомить преподавателя
            try:
                await context.bot.send_message(
                    old_teacher[0],
                    f"📢 Зміна призначення\n\n"
                    f"Студент {student[2]} {student[3]} більше не є вашим учнем.\n"
                    f"Призначення скасовано адміністратором."
                )
            except:
                pass
            
            # Уведомить студента
            try:
                await context.bot.send_message(
                    student_id,
                    f"👨‍🏫 Зміна викладача\n\n"
                    f"Ваше призначення з викладачем {old_teacher[2]} {old_teacher[3]} скасовано.\n"
                    f"Незабаром вам призначать нового викладача."
                )
            except:
                pass
                
        except Exception as e:
            await query.edit_message_text(f"❌ Помилка видалення викладача: {str(e)}")
        return
    
# ФІНАЛЬНИЙ КРОК: Виконання мульти-скасування
    if data.startswith("confirm_multi_cancel_"):
        print(f"\n[DEBUG] !!! БОТ ЗЛОВИВ ФІНАЛЬНУ КНОПКУ !!!")
        print(f"[DEBUG] Data кнопки: {data}")
        
        parts = data.split("_")
        # parts[0] = confirm, parts[1] = multi, parts[2] = cancel
        # parts[3] = student_id, parts[4] = lesson_ids (через двокрапку)
        
        student_id = parts[3]
        lesson_ids = parts[4].split(":")
        
        print(f"[DEBUG] Починаємо скасування для учня {student_id}. Уроки: {lesson_ids}")
        count = 0

        for l_id in lesson_ids:
            if not l_id: continue
            
            lesson = db.get_lesson_by_id(int(l_id))
            if not lesson:
                continue
            
            # 1. Скасовуємо в базі
            db.cancel_lesson(int(l_id))
            
            # 2. Форматуємо дату та час
            f_date, f_time = format_lesson_date_time(lesson[4], lesson[5])
            
            # 3. Прибираємо None з імен (індекси 9 та 10 — це вчитель)
            t_first = lesson[9] if lesson[9] else ""
            t_last = lesson[10] if lesson[10] else ""
            t_full = f"{t_first} {t_last}".strip() or "Викладач"

            # 4. Надсилаємо повідомлення
            try:
                # ПОВІДОМЛЕННЯ УЧНЮ
                if lesson[2]: # індивідуальний
                    await context.bot.send_message(
                        lesson[2], 
                        f"❌ Урок скасовано адміністрацією\n"
                        f"📅 {f_date} о {f_time}\n"
                        f"👨‍🏫 Викладач: {t_full}"
                    )
                
                # ПОВІДОМЛЕННЯ ВИКЛАДАЧУ
                # (Для вчителя виводимо, хто був учнем — індекси 11 та 12)
                s_first = lesson[11] if lesson[11] else ""
                s_last = lesson[12] if lesson[12] else ""
                s_full = f"{s_first} {s_last}".strip() or "Учень"
                
                target = f"👨‍🎓 Учень: {s_full}" if lesson[2] else f"👥 Група: {lesson[13] or 'Невідомо'}"

                await context.bot.send_message(
                    lesson[1], 
                    f"❌ Урок скасовано адміністрацією\n"
                    f"📅 {f_date} о {f_time}\n"
                    f"{target}"
                )
            except Exception as e:
                print(f"[DEBUG] Помилка відправки повідомлення: {e}")
            
            count += 1
            print(f"[DEBUG] Урок {l_id} успішно скасовано")

        # Результат адміну
        await query.answer(f"✅ Скасовано уроків: {count}", show_alert=True)
        await query.edit_message_text(
            f"✅ Успішно скасовано уроків: **{count}**\n\nВсі учасники отримали повідомлення.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ До розкладу", callback_data=f"admin_student_{student_id}")]]),
            parse_mode="Markdown"
        )
        print(f"[DEBUG] Фініш! Скасовано всього: {count}")
        return

    # Чат з викладачем
    if data.startswith("chat_teacher_"):
        teacher_id = int(data.split("_")[2])
        context.user_data['chat_with'] = teacher_id
        context.user_data['chat_type'] = 'individual'
        teacher = db.get_user(teacher_id)
        await query.edit_message_text(
            f"💬 Чат з викладачем {teacher[2]} {teacher[3]}\n\n"
            "Напишіть ваше повідомлення:"
        )
        return
    
    # Чат з групою
    if data.startswith("chat_group_"):
        group_id = int(data.split("_")[2])
        context.user_data['chat_with_group'] = group_id
        context.user_data['chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        await query.edit_message_text(
            f"👥 Чат з групою {group[1] if group else 'Невідомо'}\n\n"
            "Напишіть ваше повідомлення:"
        )
        return
    
    # Скасування чатів
    if data in ["cancel_chat", "cancel_teacher_chat"]:
        await query.edit_message_text("Скасовано.")
        return
    
    # Розклад викладача
    if data == "schedule_today":
        today = datetime.now().date()
        lessons = db.get_teacher_lessons(user_id, today)
        
        if not lessons:
            text = f"📅 Розклад на сьогодні ({today.strftime('%d.%m.%Y')})\n\n❌ Уроків немає"
        else:
            text = f"📅 Розклад на сьогодні ({today.strftime('%d.%m.%Y')})\n\n"
            for lesson in lessons:
                lesson_time = format_lesson_time(lesson[5])  # ИСПРАВЛЕНО: lesson_time это индекс 5
                if lesson[2]:  # individual lesson
                    student_name = f"{lesson[9]} {lesson[10]}" if lesson[9] and lesson[10] else "Невідомо"  # ИСПРАВЛЕНО: индексы 9,10
                    text += f"📚 Час: {lesson_time}\n"
                    text += f"    👨‍🎓 Учень: {student_name} (індивідуально)\n\n"
                else:  # group lesson
                    group_name = lesson[11] if lesson[11] else "Невідомо"  # ИСПРАВЛЕНО: group_name это индекс 11
                    text += f"📚 Час: {lesson_time}\n"
                    text += f"    👥 Група: {group_name}\n\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Розклад на тиждень (викладач)
    if data == "schedule_week":
        lessons = db.get_teacher_lessons(user_id)
        
        if not lessons:
            text = "📆 Розклад на тиждень\n\n❌ Уроків немає"
        else:
            text = "📆 Розклад на тиждень\n\n"
            current_date = None
            for lesson in lessons[:14]:
                lesson_date = lesson[4]
                
                if lesson_date != current_date:
                    current_date = lesson_date
                    try:
                        date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        weekday_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
                        weekday = weekday_names[date_obj.weekday()]
                        text += f"\n📅 {formatted_date} ({weekday})\n"
                    except:
                        text += f"\n📅 {current_date}\n"
                
                lesson_time = format_lesson_time(lesson[5])
                
                # --- ОНОВЛЕНА ЛОГІКА ВИВОДУ (УЧЕНЬ АБО ГРУПА) ---
                if lesson[2]:  # Індивідуальний учень
                    first_name = lesson[9] if (len(lesson) > 9 and lesson[9]) else ""
                    last_name = lesson[10] if (len(lesson) > 10 and lesson[10]) else ""
                    full_name = f"{first_name} {last_name}".strip()
                    student_name = full_name if full_name else "Учень"
                    
                    text += f"  📚 Час: {lesson_time}\n"
                    text += f"      👨‍🎓 Учень: {student_name} (індивідуально)\n"
                
                elif lesson[3]:  # Груповий урок
                    g_id = lesson[3]
                    # Намагаємось дістати назву групи з бази за її ID
                    group_info = db.get_group(g_id)
                    if group_info:
                        g_name = group_info[1] # Індекс 1 — це зазвичай назва групи
                    else:
                        # Якщо в базі не знайшли, пробуємо взяти з результату запиту
                        g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Група"
                    
                    text += f"  📚 Час: {lesson_time}\n"
                    text += f"      👥 Група: {g_name}\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Календар викладача
    if data == "schedule_calendar":
        now = datetime.now()
        calendar_keyboard = get_calendar_keyboard(now.year, now.month)
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду розкладу:",
            reply_markup=calendar_keyboard
        )
        return
    
    if data.startswith("admin_select_student"):
        # Определяем текущую страницу (по умолчанию 0)
        page = int(data.split("_")[3]) if len(data.split("_")) > 3 else 0
        items_per_page = 10  # Кол-во учеников на одной странице
        
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
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 {student[2]} {student[3]}{teacher_info}",
                callback_data=f"admin_student_{student[0]}"
            )])

        # Кнопки навигации
        navigation_buttons = []
        if page > 0:
            navigation_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_select_student_{page - 1}"))
        
        # Показываем номер страницы
        navigation_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
        
        if end_idx < len(students):
            navigation_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"admin_select_student_{page + 1}"))
        
        if navigation_buttons:
            keyboard.append(navigation_buttons)

        keyboard.append([InlineKeyboardButton("🔍 Пошук за ім'ям", callback_data="admin_search_student_schedule")])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])
        
        await query.edit_message_text(
            f"Оберіть учня (всього {len(students)}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "admin_search_student_schedule":
        context.user_data['waiting_for_admin_student_search'] = True
        await query.edit_message_text(
            "🔎 Введіть ім'я або прізвище учня (або частину):\n\n"
            "Бот знайде всіх учнів, у яких є це слово в імені або прізвищі."
        )
        return

    if data == "admin_select_teacher":
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
                callback_data=f"admin_teacher_{teacher[0]}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])
        
        await query.edit_message_text(
            "Оберіть викладача:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data == "admin_select_group":
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
                callback_data=f"admin_group_{group[0]}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_admin_schedule")])
        
        await query.edit_message_text(
            "Оберіть групу:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Просмотр расписания конкретного студента/преподавателя/группы
    # --- РОЗКЛАД УЧНЯ ---
    if data.startswith("admin_student_"):
        student_id = int(data.split("_")[2])
        student = db.get_user(student_id)
        # Отримуємо уроки
        lessons = db.get_active_lessons_for_student(student_id)
        
        student_full_name = f"{student[2] or ''} {student[3] or ''}".strip()
        
        if not lessons:
            text = f"📅 Розклад учня {student_full_name}\n\n❌ Активних уроків немає"
        else:
            text = f"📅 Розклад учня {student_full_name}\n\n"
            for lesson in lessons[:15]:
                l_date = lesson[4]
                l_time = lesson[5][:5] if lesson[5] else "??:??"
                
                # Отримуємо ПОВНЕ ім'я викладача через його ID
                t_id = lesson[1] 
                teacher = db.get_user(t_id)
                
                if teacher:
                    t_full = f"{teacher[2] or ''} {teacher[3] or ''}".strip()
                else:
                    t_first = lesson[9] if len(lesson) > 9 and lesson[9] else ""
                    t_last = lesson[10] if len(lesson) > 10 and lesson[10] else ""
                    t_full = f"{t_first} {t_last}".strip() or "Викладач"
                
                text += f"📚 {l_date} о {l_time} — викладач: {t_full}\n"
        
        # КНОПКИ (Яких не вистачало)
        keyboard = [
            [InlineKeyboardButton("➕ Додати урок", callback_data=f"admin_add_lesson_student_{student_id}")],
            [InlineKeyboardButton("🗑 Скасувати урок", callback_data=f"admin_cancel_student_{student_id}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_select_student")]
        ]
        
        # ВІДПРАВКА (Якої не вистачало)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return # Важливо, щоб код не йшов далі в блок викладача
    
    # --- РОЗКЛАД ВИКЛАДАЧА ---
    if data.startswith("admin_teacher_"):
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
                
                # ЛОГІКА ВИЗНАЧЕННЯ: УЧЕНЬ ЧИ ГРУПА
                if lesson[2]:  # Якщо є ID учня (індивідуально)
                    s_id = lesson[2]
                    student = db.get_user(s_id)
                    if student:
                        s_full = f"{student[2] or ''} {student[3] or ''}".strip()
                    else:
                        s_full = "Учень"
                    text += f"📚 {l_date} о {l_time} — з: {s_full}\n"
                
                elif lesson[3]:  # Якщо є ID групи (групове заняття)
                    g_id = lesson[3]
                    # Спробуємо отримати назву групи з бази
                    group_data = db.get_group(g_id) # Переконайся, що в db є функція get_group
                    if group_data:
                        g_name = group_data[1] # Зазвичай індекс 1 — це назва
                    else:
                        # Резервний варіант, якщо get_group не повернув дані
                        g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Група"
                    
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

    # --- РОЗКЛАД ГРУПИ ---
    if data.startswith("admin_group_"):
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
                
                # Отримуємо ПОВНЕ ім'я викладача групи
                t_id = lesson[1]
                teacher = db.get_user(t_id)
                if teacher:
                    t_full = f"{teacher[2] or ''} {teacher[3] or ''}".strip()
                else:
                    t_full = f"{lesson[9] or ''} {lesson[10] or ''}".strip() or "Викладач"
                
                text += f"{status_icon} {l_date} о {l_time} — викладач: {t_full}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Додати урок", callback_data=f"admin_add_lesson_group_{group_id}")],
            [InlineKeyboardButton("🗑 Скасувати урок", callback_data=f"admin_cancel_group_{group_id}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="admin_select_group")]
        ]
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Добавление урока админом
    if data.startswith("admin_add_lesson_"):
        parts = data.split("_")
        entity_type = parts[3]  # student, teacher, group
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
                f"➕ Додавання уроку для учня {student[2]} {student[3]}\n"
                f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n\n"
                "Введіть дату уроку в форматі ДД.ММ.РРРР:"
            )
        elif entity_type == "teacher":
            teacher = db.get_user(entity_id)
            context.user_data['admin_lesson_teacher_id'] = entity_id
            
            # Показать выбор между студентами и группами этого преподавателя
            students = db.get_teacher_students(entity_id)
            groups = db.get_teacher_groups(entity_id)
            
            if not students and not groups:
                await query.edit_message_text("❌ У викладача немає учнів та груп.")
                return
            
            keyboard = []
            for student in students:
                keyboard.append([InlineKeyboardButton(
                    f"👨‍🎓 {student[2]} {student[3]}",
                    callback_data=f"admin_select_lesson_student_{student[0]}"
                )])
            for group in groups:
                keyboard.append([InlineKeyboardButton(
                    f"👥 {group[1]}",
                    callback_data=f"admin_select_lesson_group_{group[0]}"
                )])
            keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"admin_teacher_{entity_id}")])
            
            await query.edit_message_text(
                f"➕ Додавання уроку для викладача {teacher[2]} {teacher[3]}\n\n"
                "Оберіть учня або групу:",
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
                f"➕ Додавання уроку для групи {group[1]}\n\n"
                "Введіть дату уроку в форматі ДД.ММ.РРРР:"
            )
        
        return ADMIN_ADD_LESSON_DATE
    
    # Выбор студента/группы для урока преподавателя
    if data.startswith("admin_select_lesson_"):
        parts = data.split("_")
        target_type = parts[3]  # student или group
        target_id = int(parts[4])
        
        context.user_data['admin_lesson_target_type'] = target_type
        context.user_data['admin_lesson_target_id'] = target_id
        # Sync keys so admin_add_lesson_time can read them correctly
        context.user_data['admin_lesson_entity_type'] = target_type
        context.user_data['admin_lesson_entity_id'] = target_id
        
        if target_type == "student":
            student = db.get_user(target_id)
            teacher = db.get_user(context.user_data['admin_lesson_teacher_id'])
            await query.edit_message_text(
                f"➕ Додавання уроку\n"
                f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
                f"👨‍🎓 Учень: {student[2]} {student[3]}\n\n"
                "Введіть дату уроку в форматі ДД.ММ.РРРР:"
            )
        else:  # group
            groups = db.get_all_groups()
            group = next((g for g in groups if g[0] == target_id), None)
            teacher = db.get_user(context.user_data['admin_lesson_teacher_id'])
            await query.edit_message_text(
                f"➕ Додавання уроку\n"
                f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
                f"👥 Група: {group[1] if group else 'Невідомо'}\n\n"
                "Введіть дату уроку в форматі ДД.ММ.РРРР:"
            )
        
        return ADMIN_ADD_LESSON_DATE
    
    if data == "back_admin_schedule":
        keyboard = [
            [InlineKeyboardButton("👨‍🎓 Обрати учня", callback_data="admin_select_student")],
            [InlineKeyboardButton("👨‍🏫 Обрати викладача", callback_data="admin_select_teacher")],
            [InlineKeyboardButton("👥 Обрати групу", callback_data="admin_select_group")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "🗓 Керування розкладом\n\nОберіть тип пошуку:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "student_schedule_week":
        lessons = db.get_student_lessons(user_id)
        
        if not lessons:
            text = "📅 Мій календар на тиждень\n\n❌ Уроків немає"
        else:
            text = "📅 Мій календар на тиждень\n\n"
            current_date = None
            for lesson in lessons[:14]:  # Обмежуємо до 14 уроків
                lesson_date = lesson[4]  
                
                if lesson_date != current_date:
                    current_date = lesson_date
                    try:
                        date_obj = datetime.strptime(lesson_date, '%Y-%m-%d').date()
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        weekday_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
                        weekday = weekday_names[date_obj.weekday()]
                        text += f"\n📅 {formatted_date} ({weekday})\n"
                    except (ValueError, TypeError):
                        text += f"\n📅 {lesson_date}\n"
                
                # --- ВИПРАВЛЕНО: Чистимо ім'я викладача від None ---
                lesson_time = format_lesson_time(lesson[5])
                t_first = lesson[9] if lesson[9] else ""
                t_last = lesson[10] if lesson[10] else ""
                teacher_name = f"{t_first} {t_last}".strip() or "Викладач"
                
                # Визначаємо тип уроку
                if lesson[2]:  # індивідуально
                    lesson_type = "індивідуально"
                else:  # група
                    g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                    lesson_type = f"група {g_name}"
                
                text += f"  📚 Час: {lesson_time}\n"
                text += f"      👨‍🏫 Викладач: {teacher_name}\n"
                text += f"      📋 Тип: {lesson_type}\n\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_student_schedule")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Календар студента
    if data == "student_schedule_calendar":
        now = datetime.now()
        calendar_keyboard = get_calendar_keyboard(now.year, now.month)
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду календаря:",
            reply_markup=calendar_keyboard
        )
        return
    
    # Навігація календаря
    if data.startswith("cal_"):
        if data.startswith("cal_prev_"):
            year, month = map(int, data.split("_")[2:4])
            calendar_keyboard = get_calendar_keyboard(year, month)
            await query.edit_message_reply_markup(reply_markup=calendar_keyboard)
            return
        
        elif data.startswith("cal_next_"):
            year, month = map(int, data.split("_")[2:4])
            calendar_keyboard = get_calendar_keyboard(year, month)
            await query.edit_message_reply_markup(reply_markup=calendar_keyboard)
            return
        
        elif data == "cal_today":
            now = datetime.now()
            calendar_keyboard = get_calendar_keyboard(now.year, now.month)
            await query.edit_message_reply_markup(reply_markup=calendar_keyboard)
            return
        
        # ПРАВИЛЬНАЯ замена в функции button_callback для календаря на конкретную дату

        elif data.startswith("cal_date_"):
            year, month, day = map(int, data.split("_")[2:5])
            selected_date = datetime(year, month, day).date()
            
            # Показать расписание на выбранную дату
            if user[4] == 'teacher':
                lessons = db.get_teacher_lessons(user_id, selected_date)
                if not lessons:
                    text = f"📅 Розклад на {selected_date.strftime('%d.%m.%Y')}\n\n❌ Уроків немає"
                else:
                    text = f"📅 Розклад на {selected_date.strftime('%d.%m.%Y')}\n\n"
                    for lesson in lessons:
                        lesson_time = format_lesson_time(lesson[5])
                        
                        # ВИЗНАЧЕННЯ ТИПУ ТА ІМЕНІ УЧНЯ/ГРУПИ
                        if lesson[2]:  # Якщо є student_id (індивідуально)
                            s_first = lesson[9] if lesson[9] else ""
                            s_last = lesson[10] if lesson[10] else ""
                            student_name = f"{s_first} {s_last}".strip() or "Учень"
                            
                            text += f"📚 Час: {lesson_time}\n"
                            text += f"    👨‍🎓 Учень: {student_name} (індивідуально)\n\n"
                        else:  # Якщо індивідуального учня немає, значить це група
                            group_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                            text += f"📚 Час: {lesson_time}\n"
                            text += f"    👥 Група: {group_name}\n\n"
            
            else:  # Розклад для СТУДЕНТА
                lessons = db.get_student_lessons(user_id, selected_date)
                if not lessons:
                    text = f"📅 Календар на {selected_date.strftime('%d.%m.%Y')}\n\n❌ Уроків немає"
                else:
                    text = f"📅 Календар на {selected_date.strftime('%d.%m.%Y')}\n\n"
                    for lesson in lessons:
                        lesson_time = format_lesson_time(lesson[5])
                        
                        # Ім'я викладача (індекси 9, 10)
                        t_first = lesson[9] if lesson[9] else ""
                        t_last = lesson[10] if lesson[10] else ""
                        teacher_name = f"{t_first} {t_last}".strip() or "Викладач"
                        
                        # ВИЗНАЧЕННЯ ТИПУ ДЛЯ УЧНЯ
                        if lesson[2]:  # індивідуально
                            lesson_type = "індивідуально"
                        else:  # група
                            g_name = lesson[11] if (len(lesson) > 11 and lesson[11]) else "Невідома"
                            lesson_type = f"група {g_name}"
                        
                        text += f"📚 Час: {lesson_time}\n"
                        text += f"    👨‍🏫 Викладач: {teacher_name}\n"
                        text += f"    📋 Тип: {lesson_type}\n\n"
            
            keyboard = [[InlineKeyboardButton("⬅️ Назад до календаря", callback_data=f"back_to_calendar_{year}_{month}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return
    
    # Повернення до календаря
    if data.startswith("back_to_calendar_"):
        year, month = map(int, data.split("_")[3:5])
        calendar_keyboard = get_calendar_keyboard(year, month)
        await query.edit_message_text(
            "📅 Оберіть дату для перегляду розкладу:",
            reply_markup=calendar_keyboard
        )
        return
    
    # Повернення до розкладу
    if data == "back_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "📆 Мій розклад\n\nОберіть період для перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data == "back_student_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="student_schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "🗓 Мій календар\n\nОберіть формат перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data == "back_to_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "📆 Мій розклад\n\nОберіть період для перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Додавання уроку - вибір студента/групи
    if data.startswith("lesson_student_"):
        student_id = int(data.split("_")[2])
        context.user_data['lesson_student_id'] = student_id
        context.user_data['lesson_type'] = 'individual'
        student = db.get_user(student_id)
        
        await query.edit_message_text(
            f"➕ Додавання уроку для {student[2]} {student[3]}\n\n"
            "Введіть дату уроку в форматі ДД.ММ.РРРР:"
        )
        return ADD_LESSON_DATE
    
    if data.startswith("lesson_group_"):
        group_id = int(data.split("_")[2])
        context.user_data['lesson_group_id'] = group_id
        context.user_data['lesson_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        
        await query.edit_message_text(
            f"➕ Додавання уроку для групи {group[1] if group else 'Невідомо'}\n\n"
            "Введіть дату уроку в форматі ДД.ММ.РРРР:"
        )
        return ADD_LESSON_DATE
    
    if data == "cancel_add_lesson":
        await query.edit_message_text("Додавання уроку скасовано.")
        return ConversationHandler.END
    

    # Чат викладача з учнями
    if data.startswith("teacher_chat_student_"):
        
        # --- 1. Сохранение данных и получение информации ---
        student_id = int(data.split("_")[3])
        context.user_data['teacher_chat_with'] = student_id
        context.user_data['teacher_chat_type'] = 'individual'
        student = db.get_user(student_id)
        
        # --- 2. Очищаем старое Inline-сообщение ---
        await query.edit_message_text(
            f"✅ Чат з учнем {student[2]} {student[3]} розпочато.",
            reply_markup=None # Убираем Inline-клавиатуру, чтобы избежать ошибки
        )
        
        # --- 3. Отправляем НОВОЕ сообщение с Reply-клавиатурой ---
        # (Это нужно для отображения кнопки "Завершити діалог 🔚" под полем ввода)
        await context.bot.send_message(
            query.from_user.id,
            "Напишіть ваше повідомлення:",
            reply_markup=get_chat_active_keyboard()
        )
        
        # --- 4. Переходим в состояние активного чата ---
        return TEACHER_CHAT_ACTIVE
    
   # Чат викладача з групою
    if data.startswith("teacher_chat_group_"):
        
        # --- 1. Сохранение данных и получение информации ---
        group_id = int(data.split("_")[3])
        context.user_data['teacher_chat_with_group'] = group_id
        context.user_data['teacher_chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        group_name = group[1] if group else 'Невідомо'
        
        # --- 2. Очищаем старое Inline-сообщение ---
        # Сначала редактируем предыдущее Inline-сообщение, чтобы убрать кнопки
        await query.edit_message_text(
            f"✅ Чат з групою {group_name} розпочато.",
            reply_markup=None # Убираем Inline-клавиатуру
        )
        
        # --- 3. Отправляем НОВОЕ сообщение с Reply-клавиатурой ---
        # Это отображает кнопку "Завершити діалог 🔚" под полем ввода.
        await context.bot.send_message(
            query.from_user.id,
            "Напишіть ваше повідомлення:",
            reply_markup=get_chat_active_keyboard()
        )
        
        # --- 4. Переходим в состояние активного чата ---
        return TEACHER_CHAT_ACTIVE
    
    # Керування групами
    if data == "create_group":
        await query.edit_message_text("Введіть назву групи:")
        context.user_data['creating_group'] = True
        return CREATE_GROUP_NAME
    
    if data == "list_groups":
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
    
    if data == "edit_group":
        groups = db.get_all_groups()
        if not groups:
            await query.edit_message_text("Груп для редагування немає.")
            return
        
        keyboard = []
        for group in groups:
            keyboard.append([InlineKeyboardButton(
                f"✏️ {group[1]} ({group[3]})",
                callback_data=f"edit_group_{group[0]}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_groups")])
        
        await query.edit_message_text(
            "Оберіть групу для редагування:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("edit_group_"):
        group_id = int(data.split("_")[2])
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        
        keyboard = [
            [InlineKeyboardButton("👨‍🏫 Змінити викладача", callback_data=f"change_teacher_{group_id}")],
            [InlineKeyboardButton("👥 Керування учасниками", callback_data=f"manage_members_{group_id}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="edit_group")]
        ]
        
        await query.edit_message_text(
            f"✏️ Редагування групи: {group[1] if group else 'Невідомо'}\n\n"
            "Оберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("change_teacher_"):
        parts = data.split("_")
        # Формат: change_teacher_{group_id}_{page}
        group_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        teachers = db.get_users_by_role('teacher')
        if not teachers:
            await query.edit_message_text("Немає доступних викладачів.")
            return

        PAGE_SIZE = 10
        total_pages = (len(teachers) + PAGE_SIZE - 1) // PAGE_SIZE
        start = page * PAGE_SIZE
        chunk = teachers[start : start + PAGE_SIZE]

        keyboard = []
        for t in chunk:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🏫 {t[2]} {t[3]}",
                callback_data=f"set_teacher_{group_id}_{t[0]}"
            )])

        # Кнопки навігації для викладачів
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"change_teacher_{group_id}_{page-1}"))
        
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
        
        if (start + PAGE_SIZE) < len(teachers):
            nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"change_teacher_{group_id}_{page+1}"))
        
        if nav:
            keyboard.append(nav)
            
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"edit_group_{group_id}")])
        
        await query.edit_message_text(
            f"Оберіть нового викладача (Сторінка {page+1}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("set_teacher_"):
        parts = data.split("_")
        group_id = int(parts[2])
        teacher_id = int(parts[3])
        
        # Виконуємо зміну в базі
        db.change_group_teacher(group_id, teacher_id)
        teacher = db.get_user(teacher_id)
        
        # Створюємо кнопку, щоб адмін міг одразу повернутися до налаштувань цієї групи
        keyboard = [[InlineKeyboardButton("🔙 Назад до меню групи", callback_data=f"edit_group_{group_id}")]]
        
        await query.edit_message_text(
            f"✅ Викладача групи змінено на: {teacher[2]} {teacher[3]}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("manage_members_"):
        group_id = int(data.split("_")[2])
        members = db.get_group_members(group_id)
        group = db.get_group(group_id)
        
        keyboard = [[InlineKeyboardButton("➕ Додати учасника", callback_data=f"add_member_{group_id}_0")]]
        
        for member in members:
            keyboard.append([InlineKeyboardButton(
                f"❌ Видалити {member[2]} {member[3]}",
                callback_data=f"remove_member_{group_id}_{member[0]}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edit_group_{group_id}")])
        
        await query.edit_message_text(
            f"👥 Керування групою: {group[1]}\nУчасників: {len(members)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # ДОДАВАННЯ З ПАГІНАЦІЄЮ
    if data.startswith("add_member_"):
        parts = data.split("_")
        group_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        students = db.get_users_by_role('student')
        current_members = [m[0] for m in db.get_group_members(group_id)]
        available_students = [s for s in students if s[0] not in current_members]
        
        if not available_students:
            await query.edit_message_text(
                "Немає доступних учнів для додавання.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=f"manage_members_{group_id}")]])
            )
            return
        
        PAGE_SIZE = 10
        total_pages = (len(available_students) + PAGE_SIZE - 1) // PAGE_SIZE
        chunk = available_students[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        
        keyboard = []
        for student in chunk:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 {student[2]} {student[3]}",
                callback_data=f"add_student_{group_id}_{student[0]}_{page}"
            )])

        # Навігація
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"add_member_{group_id}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
        if (page + 1) * PAGE_SIZE < len(available_students):
            nav.append(InlineKeyboardButton("➡️", callback_data=f"add_member_{group_id}_{page+1}"))
        if nav: keyboard.append(nav)
            
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"manage_members_{group_id}")])
        
        await query.edit_message_text(
            f"Оберіть учня (Стор. {page+1} з {total_pages}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("add_student_"):
        parts = data.split("_")
        group_id, student_id, page = int(parts[2]), int(parts[3]), int(parts[4])
        
        db.add_student_to_group(group_id, student_id)
        student = db.get_user(student_id)
        
        # Повертаємося назад до списку додавання на ту ж сторінку
        keyboard = [[InlineKeyboardButton("🔙 Додати ще учнів", callback_data=f"add_member_{group_id}_{page}")],
                    [InlineKeyboardButton("✅ Готово", callback_data=f"manage_members_{group_id}")]]
        
        await query.edit_message_text(
            f"✅ Учня {student[2]} {student[3]} додано!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("remove_member_"):
        parts = data.split("_")
        group_id, student_id = int(parts[2]), int(parts[3])
        
        db.remove_student_from_group(group_id, student_id)
        
        data = f"manage_members_{group_id}"
        # (Далі спрацює блок manage_members_ і оновить список)
    
    if data == "back_groups":
        keyboard = [
            [InlineKeyboardButton("➕ Створити групу", callback_data="create_group")],
            [InlineKeyboardButton("👥 Список груп", callback_data="list_groups")],
            [InlineKeyboardButton("✏️ Змінити групу", callback_data="edit_group")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(
            "👥 Керування групами\n\nОберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Створення групи
    if data.startswith("group_type_"):
        group_type = data.split("_")[2]
        context.user_data['group_type'] = group_type
        
        teachers = db.get_users_by_role('teacher')
        if not teachers:
            await query.edit_message_text("Немає доступних викладачів.")
            return ConversationHandler.END
        
        keyboard = []
        for teacher in teachers:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🏫 {teacher[2]} {teacher[3]}",
                callback_data=f"select_group_teacher_{teacher[0]}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])
        
        await query.edit_message_text(
            f"Група: {context.user_data['group_name']} ({group_type})\n\n"
            "Оберіть викладача:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CREATE_GROUP_TEACHER
    
    if data.startswith("select_group_teacher_"):
        teacher_id = int(data.split("_")[3])
        context.user_data['group_teacher_id'] = teacher_id
        context.user_data['selected_students'] = []
        context.user_data['current_page'] = 0  # Начинаем с первой страницы
        
        teacher = db.get_user(teacher_id)
        students = db.get_users_by_role('student')
        
        if not students:
            await query.edit_message_text("Немає доступних учнів.")
            return ConversationHandler.END

        # Прямой расчет клавиатуры для первой страницы (вместо вызова несуществующей функции)
        PAGE_SIZE = 10
        current_students_chunk = students[0:PAGE_SIZE]
        
        keyboard = []
        for student in current_students_chunk:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🎓 {student[2]} {student[3]}",
                callback_data=f"toggle_student_{student[0]}"
            )])
        
        # Добавляем навигацию "Вперед", если учеников больше 10
        if len(students) > PAGE_SIZE:
            keyboard.append([InlineKeyboardButton("Вперед ➡️", callback_data="student_page_1")])

        keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])
        
        await query.edit_message_text(
            f"Група: {context.user_data['group_name']}\n"
            f"Викладач: {teacher[2]} {teacher[3]}\n\n"
            "Оберіть учнів (сторінка 1):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CREATE_GROUP_STUDENTS
    
    if data.startswith("toggle_student_"):
        student_id = int(data.split("_")[2])
        selected = context.user_data.get('selected_students', [])
        current_page = context.user_data.get('current_page', 0)
        
        if student_id in selected:
            selected.remove(student_id)
        else:
            selected.append(student_id)
        
        context.user_data['selected_students'] = selected
        
        # Оновити клавіатуру (Пагінація)
        students = db.get_users_by_role('student')
        PAGE_SIZE = 10
        start = current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        current_students_chunk = students[start:end]

        keyboard = []
        for student in current_students_chunk:
            is_selected = student[0] in selected
            prefix = "✅ " if is_selected else "👨‍🎓 "
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{student[2]} {student[3]}",
                callback_data=f"toggle_student_{student[0]}"
            )])
        
        # Кнопки навігації
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"student_page_{current_page - 1}"))
        if end < len(students):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"student_page_{current_page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])
        
        teacher = db.get_user(context.user_data['group_teacher_id'])
        selected_names = []
        for s_id in selected:
            s_obj = db.get_user(s_id)
            if s_obj:
                selected_names.append(f"{s_obj[2]} {s_obj[3]}")
        
        text = (f"Група: {context.user_data['group_name']}\n"
               f"Викладач: {teacher[2]} {teacher[3]}\n"
               f"Обрано учнів: {len(selected)}\n"
               f"Сторінка: {current_page + 1}\n")
        if selected_names:
            text += f"Учні: {', '.join(selected_names)}\n"
        text += "\nОберіть учнів (можна обрати декілька):"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return CREATE_GROUP_STUDENTS

    if data.startswith("student_page_"):
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
            keyboard.append([InlineKeyboardButton(
                f"{prefix}{student[2]} {student[3]}",
                callback_data=f"toggle_student_{student[0]}"
            )])

        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"student_page_{current_page - 1}"))
        if end < len(students):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"student_page_{current_page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("✅ Створити групу", callback_data="finish_create_group")])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_create_group")])

        teacher = db.get_user(context.user_data['group_teacher_id'])
        text = (f"Група: {context.user_data['group_name']}\n"
                f"Викладач: {teacher[2]} {teacher[3]}\n"
                f"Обрано учнів: {len(selected)}\n"
                f"Сторінка: {current_page + 1}\n\n"
                "Оберіть учнів:")

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return CREATE_GROUP_STUDENTS
    
    if data == "finish_create_group":
        selected_students = context.user_data.get('selected_students', [])
        if not selected_students:
            await query.edit_message_text("❌ Потрібно обрати хоча б одного учня.")
            return CREATE_GROUP_STUDENTS
        
        # Створити групу
        group_id = db.create_group(
            context.user_data['group_name'],
            context.user_data['group_teacher_id'],
            context.user_data['group_type']
        )
        
        # Додати студентів до групи
        for student_id in selected_students:
            db.add_student_to_group(group_id, student_id)
        
        teacher = db.get_user(context.user_data['group_teacher_id'])
        await query.edit_message_text(
            f"✅ Групу створено!\n\n"
            f"📚 Назва: {context.user_data['group_name']}\n"
            f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
            f"👥 Учнів: {len(selected_students)}"
        )
        
        # Повідомити викладача
        try:
            await context.bot.send_message(
                context.user_data['group_teacher_id'],
                f"👥 Вам призначено нову групу: {context.user_data['group_name']}"
            )
        except:
            pass
        
        # Повідомити студентів
        for student_id in selected_students:
            try:
                await context.bot.send_message(
                    student_id,
                    f"👥 Вас додано до групи: {context.user_data['group_name']}\n"
                    f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}"
                )
            except:
                pass
        
        return ConversationHandler.END
    
    if data == "cancel_create_group":
        await query.edit_message_text("Створення групи скасовано.")
        return ConversationHandler.END
    
    # Адміністративні функції
    if data == "add_teacher":
        await query.edit_message_text("Введіть ID користувача, якого хочете зробити викладачем:")
        context.user_data['waiting_for_teacher_id'] = True
        return
    
    if data == "assign_teacher":
        teachers = db.get_users_by_role('teacher')
        if not teachers:
            await query.edit_message_text("Немає викладачів для призначення.")
            return
        
        keyboard = []
        for teacher in teachers:
            keyboard.append([InlineKeyboardButton(
                f"👨‍🏫 {teacher[2]} {teacher[3]}", 
                callback_data=f"select_teacher_{teacher[0]}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "🔗 Призначити викладача\n\nОберіть викладача:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("select_teacher_") and not data.startswith("select_teacher_students_page_"):
        teacher_id = int(data.split("_")[2])
        context.user_data['selected_teacher_id'] = teacher_id
        # Переходимо на сторінку 0 через уніфікований обробник
        data = f"select_teacher_students_page_{teacher_id}_0"
        # (далі обробляє наступний блок)

    if data.startswith("select_teacher_students_page_"):
        parts = data.split("_")
        # формат: select_teacher_students_page_{teacher_id}_{page}
        teacher_id = int(parts[4])
        page = int(parts[5]) if len(parts) > 5 else 0
        context.user_data['selected_teacher_id'] = teacher_id
        teacher = db.get_user(teacher_id)

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

        # Навігація
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"select_teacher_students_page_{teacher_id}_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page + 1} / {total_pages}", callback_data="ignore"))
        if (start_idx + items_per_page) < len(students):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"select_teacher_students_page_{teacher_id}_{page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_to_menu")])

        await query.edit_message_text(
            f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n\nОберіть учня (сторінка {page + 1} з {total_pages}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("assign_to_student_"):
        student_id = int(data.split("_")[3])
        teacher_id = context.user_data.get('selected_teacher_id')
        
        if not teacher_id:
            await query.edit_message_text("Помилка: викладач не обраний.")
            return
        
        try:
            db.assign_teacher_to_student(teacher_id, student_id)
            teacher = db.get_user(teacher_id)
            student = db.get_user(student_id)
            
            await query.edit_message_text(
                f"✅ Призначення завершено!\n\n"
                f"👨‍🏫 Викладач: {teacher[2]} {teacher[3]}\n"
                f"👨‍🎓 Учень: {student[2]} {student[3]}"
            )
            
            # Повідомити викладача
            try:
                await context.bot.send_message(
                    teacher_id,
                    f"👨‍🎓 Вам призначено нового учня:\n{student[2]} {student[3]}"
                )
            except:
                pass
            
            # Повідомити учня
            try:
                await context.bot.send_message(
                    student_id,
                    f"👨‍🏫 Вам призначено викладача:\n{teacher[2]} {teacher[3]}"
                )
            except:
                pass
                
        except Exception as e:
            await query.edit_message_text(f"❌ Помилка призначення: {str(e)}")
        return

    # Переписки/чати

    # === Чат ученика с преподавателем (student_chat_teacher_) ===
    if data.startswith("student_chat_teacher_"):
        teacher_id = int(data.split("_")[3])
        context.user_data['student_chat_with'] = teacher_id
        context.user_data['student_chat_type'] = 'individual'
        teacher = db.get_user(teacher_id)
        
        # 1. Очищаем старое Inline-сообщение
        await query.edit_message_text(
            f"✅ Чат з викладачем {teacher[2]} {teacher[3]} розпочато.",
            reply_markup=None
        )
        
        # 2. Отправляем НОВОЕ сообщение с Reply-клавиатурой (ВАЖНО!)
        await context.bot.send_message(
            query.from_user.id,
            "Напишіть ваше повідомлення:",
            reply_markup=get_chat_active_keyboard()
        )
        
        # Возвращаем состояние, чтобы перейти в режим активного чата
        return STUDENT_CHAT_ACTIVE 
        
    # === Чат ученика с группой (student_chat_group_) ===
    if data.startswith("student_chat_group_"):
        group_id = int(data.split("_")[3])
        context.user_data['student_chat_with_group'] = group_id
        context.user_data['student_chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        group_name = group[1] if group else 'Невідомо'
        
        # 1. Очищаем старое Inline-сообщение
        await query.edit_message_text(
            f"✅ Чат з групою {group_name} розпочато.",
            reply_markup=None
        )
        
        # 2. Отправляем НОВОЕ сообщение с Reply-клавиатурой (ВАЖНО!)
        await context.bot.send_message(
            query.from_user.id,
            "Напишіть ваше повідомлення:",
            reply_markup=get_chat_active_keyboard()
        )
        
        # Возвращаем состояние, чтобы перейти в режим активного чата
        return STUDENT_CHAT_ACTIVE

    # === Обробка кнопки СКАСУВАТИ ===
    if data == "cancel_student_chat":
        # Тут не нужно вызывать student_chat_end, т.к. ConversationHandler делает это сам в fallbacks
        # Но если вы хотите обработать это как часть states, то логика другая.
        # Для простоты и избежания конфликтов, достаточно вернуть ConversationHandler.END:
        await query.answer("Діалог скасовано.")
        user_role = db.get_user(query.from_user.id)[4] 
        await query.edit_message_text(
            "✅ Ви повернулися до головного меню.",
            reply_markup=get_main_keyboard(user_role)
        )
        return ConversationHandler.END # Завершаем ConversationHandler

# --- ВИБІР КОГО ДИВИТИСЬ (Учень/Вчитель/Група) ---
    if data.startswith("chat_by_"):
        parts = data.split("_")
        chat_type = parts[2]
        # Перевіряємо сторінку
        page = int(parts[3]) if len(parts) > 3 else 0
        
        context.user_data['chat_filter_type'] = chat_type
        items_per_page = 10 
        
        if chat_type == "student":
            users = db.get_users_by_role('student')
            # Сортування (нечутливе до регістру)
            users.sort(key=lambda x: (x[2] or "").lower()) 
            label, prefix, title = "👨‍🎓", "view_chat_student", "Оберіть учня:"
            
        elif chat_type == "teacher":
            users = db.get_users_by_role('teacher')
            users.sort(key=lambda x: (x[2] or "").lower())
            label, prefix, title = "👨‍🏫", "view_chat_teacher", "Оберіть викладача:"
            
        elif chat_type == "group":
            users = db.get_all_groups()
            label, prefix, title = "👥", "view_chat_group", "Оберіть групу:"
            
        else:
            await query.edit_message_text("Введіть дату в форматі ДД.ММ.РРРР:")
            context.user_data['waiting_for_date'] = True
            return

        if not users:
            await query.edit_message_text(f"Немає даних для {chat_type}.")
            return

        # --- ЛОГІКА ПАГІНАЦІЇ ---
        total_pages = (len(users) + items_per_page - 1) // items_per_page
        start = page * items_per_page
        end = start + items_per_page
        current_list = users[start:end]
        
        keyboard = []
        for item in current_list:
            if chat_type == "group":
                name = item[1]
            else:
                name = f"{item[2] or ''} {item[3] or ''}".strip() or "Без імені"
                
            keyboard.append([InlineKeyboardButton(
                f"{label} {name}",
                callback_data=f"{prefix}_{item[0]}"
            )])
            
        # Кнопки навігації
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_by_{chat_type}_{page-1}"))
        
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="ignore"))
        
        if end < len(users):
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"chat_by_{chat_type}_{page+1}"))
            
        if nav_buttons:
            keyboard.append(nav_buttons)
        # ДОДАЄМО КНОПКУ ПОШУКУ ТУТ
        keyboard.append([InlineKeyboardButton("🔍 Пошук за ім'ям", callback_data=f"search_chat_user_{chat_type}")])  
        keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="back_chat_menu")])
        
        await query.edit_message_text(
            f"💬 {title}\nСторінка {page+1} з {total_pages}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("search_chat_user_"):
        chat_type = data.split("_")[3]
        context.user_data['waiting_for_search_name'] = True
        context.user_data['search_chat_type'] = chat_type
        
        await query.edit_message_text(
            "🔎 **Введіть ім'я або прізвище учня (або частину):**\n\n"
            "Бот знайде всіх, у кого в імені або прізвищі є це слово.",
            parse_mode="Markdown"
        )
        return

# --- ПЕРЕГЛЯД КОНКРЕТНОГО ЧАТУ ---
    if data.startswith("view_chat_"):
        parts = data.split("_")
        user_role = db.get_user(user_id)[4] 

        messages = []
        title = ""
        entity_type = parts[2] # student, teacher або group
        
        # 1. ЛОГІКА ДЛЯ УЧНЯ
        if user_role == 'student':
            if data.startswith("view_chat_student_teacher_"):
                teacher_id = int(parts[4])
                teacher = db.get_user(teacher_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=teacher_id)
                title = f"👨‍🏫 Чат з викладачем: {teacher[2]} {teacher[3]}"
            elif data.startswith("view_chat_student_group_"):
                group_id = int(parts[4])
                group_data = db.get_group_by_id(group_id)
                messages = db.get_chat_history(group_id=group_id)
                title = f"👥 Чат групи: {group_data[1]}"
        
        # 2. ЛОГІКА ДЛЯ ВИКЛАДАЧА
        elif user_role == 'teacher':
            if data.startswith("view_chat_teacher_student_"):
                student_id = int(parts[4])
                student = db.get_user(student_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=student_id)
                title = f"👨‍🎓 Чат з учнем: {student[2]} {student[3]}"
            elif data.startswith("view_chat_teacher_group_"):
                group_id = int(parts[4])
                group_data = db.get_group_by_id(group_id)
                messages = db.get_chat_history(group_id=group_id)
                title = f"👥 Чат групи: {group_data[1]}"

        # 3. ЛОГІКА ДЛЯ АДМІНІСТРАТОРА
        elif user_role == 'admin':
            entity_id = int(parts[3])
            context.user_data['current_chat_entity_id'] = entity_id
            context.user_data['current_chat_entity_type'] = entity_type

            if entity_type == "group":
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Адмін: Чат групи {group_data[1]}"
            
            elif entity_type == "student":
                user_entity = db.get_user(entity_id)
                teacher = db.get_student_teacher(entity_id)
                if teacher:
                    messages = db.get_chat_history(user1_id=entity_id, user2_id=teacher[0])
                    title = f"👨‍🎓 Чат {user_entity[2]} з викладачем {teacher[2]}"
                else:
                    title = f"👨‍🎓 {user_entity[2]} (немає викладача)"
            
            elif entity_type == "teacher":
                user_entity = db.get_user(entity_id)
                # Збираємо всі повідомлення вчителя з його учнями
                students = db.get_teacher_students(entity_id)
                for s in students:
                    messages.extend(db.get_chat_history(user1_id=entity_id, user2_id=s[0]))
                messages.sort(key=lambda x: x[6], reverse=True) # Сортуємо за часом
                title = f"👨‍🏫 Всі чати викладача {user_entity[2]}"

        # ВИВЕДЕННЯ РЕЗУЛЬТАТУ
        if not messages:
            # Якщо адмін — повертаємо його до списку (з пагінацією), якщо ні — в меню чатів
            back_call = f"chat_by_{entity_type}_0" if user_role == 'admin' else "back_chat_menu"
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=back_call)]]
            await query.edit_message_text(f"{title}\n\n❌ Повідомлень ще немає.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Зберігаємо дані для пагінації повідомлень (show_chat_page)
        context.user_data['current_chat_messages'] = messages
        context.user_data['current_chat_title'] = title
        context.user_data['current_page'] = 0
        await show_chat_page(query, context, 0)
        return

    # --- ОБРОБНИК СТОРІНОК ПЕРЕПИСКИ ---
    if data.startswith("chat_page_"):
        page_number = int(data.split("_")[2])
        context.user_data['current_page'] = page_number
        await show_chat_page(query, context, page_number)
        return

   # 1. ОБРОБКА ПОВТОРНОГО ДОДАВАННЯ УРОКУ (Адмін)
    if data.startswith("admin_lesson_target_"):
        parts = data.split("_")
        # Очікуваний формат: admin_lesson_target_student_123 або admin_lesson_target_group_123
        # parts: [0]admin, [1]lesson, [2]target, [3]entity_type, [4]entity_id
        
        try:
            entity_type = parts[3]
            entity_id = int(parts[4])
            
            # Зберігаємо дані, щоб не перепитувати вчителя/учня
            context.user_data['admin_lesson_entity_type'] = entity_type
            context.user_data['admin_lesson_entity_id'] = entity_id
            
            await query.answer()
            
            # Визначаємо назву для тексту
            target_label = "учня" if entity_type == "student" else "групи"
            
            await query.edit_message_text(
                f"➕ Додавання ще одного уроку для {target_label}.\n\n"
                f"Введіть дату уроку (ДД.ММ.РРРР):"
            )
            
            # Повертаємо стан очікування дати, щоб активувати ConversationHandler
            return ADMIN_ADD_LESSON_DATE
            
        except (IndexError, ValueError) as e:
            print(f"Помилка парсингу admin_lesson_target: {e}")
            await query.answer("Сталася помилка. Спробуйте через меню.", show_alert=True)
            return ConversationHandler.END

    # 2. НОВИЙ БЛОК: Обробка історії чатів для студента
   






# --------------------------
# ОБРОБНИК КОМАНДИ РЕЗЕРВНОГО КОПІЮВАННЯ
# --------------------------
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

async def show_chat_page(query, context, page_number):
    messages = context.user_data.get('current_chat_messages', [])
    title = context.user_data.get('current_chat_title', '')
    entity_type = context.user_data.get('current_chat_entity_type', '')

    total_messages = len(messages)
    MESSAGES_PER_PAGE = 10 
    total_pages = (total_messages + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE

    start_index = page_number * MESSAGES_PER_PAGE
    end_index = start_index + MESSAGES_PER_PAGE

    page_messages = messages[start_index:end_index]
    
    if not page_messages:
        text = f"{title}\n\n❌ Повідомлень немає на цій сторінці"
    else:
        if entity_type == "teacher":
            teacher_name = title.replace("👨‍🏫 Історія чатів викладача ", "")
            text = f"<b>{teacher_name}</b>\n\n(Сторінка {page_number + 1} з {total_pages})\n\n"
        else:
            text = f"{title}\n\n(Сторінка {page_number + 1} з {total_pages})\n\n"

        for msg in page_messages:
            try:
                if len(msg) > 4 and isinstance(msg[4], str) and msg[4].strip():
                    message_text = msg[4]
                elif len(msg) > 3 and isinstance(msg[3], str) and msg[3].strip():
                    message_text = msg[3]
                else:
                    message_text = ""

                # ОБМЕЖЕННЯ: Якщо одне повідомлення занадто довге, обрізаємо його
                if len(message_text) > 300:
                    message_text = message_text[:297] + "..."

                dt_obj = datetime.fromisoformat(msg[6])
                dt_corrected = dt_obj + timedelta(hours=2)
                timestamp = dt_corrected.strftime("📅 %d.%m ⏰ %H:%M")

                sender_first = msg[7] if len(msg) > 7 and msg[7] else ""
                sender_role = msg[8] if len(msg) > 8 and msg[8] else ""
                sender_name = f"{sender_first} {sender_role}".strip() if sender_first or sender_role else "Невідомо"
                
                new_line = ""
                if entity_type == "teacher":
                    student_id = msg[2]
                    student_user = db.get_user(student_id)
                    student_name = f"{student_user[2]} {student_user[3]}" if student_user else "Невідомо"
                    new_line = f"<b>Кому: {student_name}</b> {timestamp} {sender_name}: {message_text}\n"
                else:
                    new_line = f"{timestamp} {sender_name}: {message_text}\n"

                # ПЕРЕВІРКА: чи влізе новий рядок у ліміт 4096 символів
                if len(text) + len(new_line) > 4000:
                    text += "\n⚠️ <i>Частина повідомлень не влізла на сторінку...</i>"
                    break
                
                text += new_line

            except Exception as e:
                print(f"Error processing message: {msg}, error: {e}")
                continue


    # Кнопки пагінації
    keyboard_row = []
    if page_number > 0:
        keyboard_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_page_{page_number - 1}"))
    if page_number < total_pages - 1:
        keyboard_row.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"chat_page_{page_number + 1}"))

    keyboard = [
        keyboard_row,
        [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_chat_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
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
            cb_back_to_list = f"admin_group_{entity_id}" # Перевірте, чи такий префікс для груп
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
    
# (Предполагаем, что get_main_keyboard и db.get_user_role доступны)

# 4. ИСПРАВЛЕНИЕ: Добавить недостающую функцию cancel_admin_lesson










async def send_manager_contact_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет кнопку для прямого перехода к чату с менеджером"""
    keyboard = [
        [InlineKeyboardButton("📞 Написати менеджеру", url="https://t.me/UKnow_Online_School")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📞 Зв'язок з менеджером\n\n"
        "Натисніть кнопку нижче щоб відкрити чат з менеджером:",
        reply_markup=reply_markup
    )

async def manager_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /manager для быстрого доступа к менеджеру"""
    await send_manager_contact_button(update, context)

from html import escape




        
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Спочатку зареєструйтеся за допомогою команди /start")
        return
    
    message_text = update.message.text
    
    # НОВАЯ ПРОВЕРКА: Ограничить доступ к админским функциям
    admin_buttons = [
        "👨‍💼 Керування користувачами",
        "👥 Керування групами", 
        "🗓 Керування розкладом",
        "🗂️ Переписки / Чати",
        "📢 Масова розсилка",
        "📊 Звіти"
    ]
    
    if message_text in admin_buttons and user[4] != 'admin':
        await update.message.reply_text("❌ У вас немає прав доступу до цієї функції.")
        return
    
    # Основні кнопки студента
    if message_text == "💬 Написати викладачеві/групі":
        # Замість write_to_teacher_or_group викликаємо нову функцію
        await student_message_start(update, context) 
        return

    elif message_text == "📞 Написати менеджеру": # <-- ВСТАВТЕ ЦЮ УМОВУ
        await send_manager_contact_button(update, context)
        return

    elif message_text == "📖 Історія переписок": # <-- ДОДАЙТЕ ЦЕЙ БЛОК
        user_id = update.effective_user.id
        await show_student_chat_history(update, context, user_id)
        return

    elif message_text == "🗓 Мій календар":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="student_schedule_today")],
            [InlineKeyboardButton("📅 На тиждень", callback_data="student_schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="student_schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(
            "🗓 Мій календар\n\nОберіть формат перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Основні кнопки викладача
    elif message_text == "📆 Мій розклад":
        keyboard = [
            [InlineKeyboardButton("📅 Сьогодні", callback_data="schedule_today")],
            [InlineKeyboardButton("📆 На тиждень", callback_data="schedule_week")],
            [InlineKeyboardButton("🗓 Календар", callback_data="schedule_calendar")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(
            "📆 Мій розклад\n\nОберіть період для перегляду:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    elif message_text == "💬 Написати учневі/групі":
        await teacher_message_students(update, context)
        return
    elif message_text == "➕ Додати урок":
        await add_lesson_start(update, context)
        return
    
    # Основні кнопки адміністратора
    elif message_text == "👥 Керування групами":
        keyboard = [
            [InlineKeyboardButton("➕ Створити групу", callback_data="create_group")],
            [InlineKeyboardButton("👥 Список груп", callback_data="list_groups")],
            [InlineKeyboardButton("✏️ Змінити групу", callback_data="edit_group")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(
            "👥 Керування групами\n\nОберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    elif message_text == "🗂️ Переписки / Чати":
        keyboard = [
            [InlineKeyboardButton("👨‍🎓 По учню", callback_data="chat_by_student")],
            [InlineKeyboardButton("👨‍🏫 По викладачу", callback_data="chat_by_teacher")],
            [InlineKeyboardButton("👥 По групі", callback_data="chat_by_group")],
            [InlineKeyboardButton("📅 По даті", callback_data="chat_by_date")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(
            "🗂️ Переписки / Чати\n\nОберіть спосіб фільтрації:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    elif message_text == "🗓 Керування розкладом":
        keyboard = [
            [InlineKeyboardButton("👨‍🎓 Обрати учня", callback_data="admin_select_student")],
            [InlineKeyboardButton("👨‍🏫 Обрати викладача", callback_data="admin_select_teacher")],
            [InlineKeyboardButton("👥 Обрати групу", callback_data="admin_select_group")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(
            "🗓 Керування розкладом\n\nОберіть тип пошуку:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    elif message_text == "🏫 Про школу":
        await update.message.reply_text(
            "🏫 Про нашу школу UKnow\n\n"
            "🇺🇦 Ми українська онлайн школа UKnow. Працюємо з 2022 року і допомагаємо українцям в різних куточках світу оволодіти мовою і інтегруватися в суспільство.\n\n"
            "🌎 Сьогодні ми пропонуємо уроки з англійської, іспанської, польської, французької, італійської, чеської, словацької, німецької та турецької мов\n\n"
            "🎉 Ми вже випустили більше 4000 студентів\n\n"
            "👨‍🏫 Наші викладачі проходять 4 етапи відбору, перед тим як приступити до занять.\n\n"
            "🎯 Ми можемо підготувати Вас до екзаменів на знання мови, до екзамену на вступ у ВНЗ, допомогти Вам заговорити за 36 уроків, або отримати найвищу оцінку при оформлені документів."
        )
        return
    elif message_text == "📋 Правила школи":
        await update.message.reply_text(
            "📋 Правила школи 🚨\n\n"
            "З повним переліком правил роботи школи ви можете ознайомитися у договорі який вам надав ваш менеджер ✅\n\n"
            "Для вашої зручності додаємо сюди основні моменти:\n\n"
            "📌 Оплата абонементу є згодою з умовами договору оферти\n"
            "📌 Школа залишає за собою право зміни викладача під час навчального процесу\n"
            "📌 Матеріали та наповнення уроку надається школою та викладачем на свій розсуд\n"
            "📌 Відміна уроку зі сторони вчителя можлива не менше ніж за 2 години до початку\n"
            "📌 Відміна уроку зі сторони учня можлива не менше ніж за 2 години до початку, у разі, якщо попередження про відміну/перенос уроку відбулося менше ніж за 2 години – урок фіксується проведеним\n"
            "📌 У разі запізнення учня на урок на 15 і більше хвилин – урок вважається проведеним\n"
            "📌 Учень має право звертатися у будь який час до представників школи для вирішення навчальних питань та консультації\n"
            "📌 Учень має право «заморозити» навчання, до трьох місяців – попередньо попередивши про це менеджера і погодивши період паузи\n"
            "📌 У разі недоукомплектування групи – школа залишає за собою право закрити групу і запропонувати учневі альтернативні варіанти навчання\n"
            "📌 У разі бажання учня розірвати договір в односторонньому порядку, через недомовленість між школою і учнем у вирішенні організаційних питань – можливе повернення у розмірі 50% від залишку коштів на момент розривання договору. Протягом 14 банківських днів\n"
            "📌 У випадку відсутності одного з учнів на парному/груповому уроці – урок вважається проведеним і надається запис уроку\n"
            "📌 Школа не несе відповідальності, якщо учень не зміг скористатися наданими послугами з причини, які не залежать від школи\n"
            "📌 Абонемент має термін дії, відповідно до кількості занять, після закінчення терміну дії абонементу – невикористані уроки списуються з балансу\n"
            "📌 Підбір пари для міні-групи займає 10-14 робочих днів\n"
            "📌 Умови бронювання навчання (термін бронювання, що викладач та графік може бути зміненим, передоплата не повертається, якщо учень передумав)"
        )
        return
    elif message_text == "❓ Популярні питання":
        await update.message.reply_text(
            "❓ Популярні питання\n\n"
            "- Чи зможу я змінювати графік?\n"
            "Так, Ви можете змінювати графік протягом навчання, попередньо обговоривши це з адміністратором.🗓\n\n"
            "- Чи можна перенести або відмінити урок?\n"
            "Так, Ви можете перенести урок, попередивши нас мінімум за 2️⃣ години до початку.\n\n"
            "- Що робити якщо викладач не прийшов на урок?\n"
            "Напишіть одразу адміністратору.☎️\n\n"
            "- Я отримаю сертифікат про навчання?\n"
            "Обов'язково! Навіть, двома мовами🏅\n\n"
            "- Куди підключатись на урок?\n"
            "В чаті закріплене стале посилання на зустріч👩🏻‍💻\n\n"
            "- Я можу змінити викладача?\n"
            "Так, Вам треба написати своє бажання адміністратору і ми запропонуємо для Вас нового викладача.👩🏻‍🏫\n\n"
            "- Чи є розмовні клуби?\n"
            "Так, з кожної мови.\n\n"
            "- Можна поставити навчання на паузу?\n"
            "Так, ми можемо заморозити навчання на термін до 3х місяців.⏸️\n\n"
            "- Куди відправляти домашнє завдання?\n"
            "Домашнє завдання надсилайте в цей чат бот \"Викладачеві\"📝\n\n"
            "- Як продовжити навчання?\n"
            "За декілька уроків до кінця навчання, Вам напише адміністратор і обговорить продовження. Або ж Ви можете написати самостійно і адміністратор надішле Вам всю інформацію стосовно продовження навчання.📚"
        )
        return
    elif message_text == "📬 Вхідні":
        if user[4] == 'teacher':
            await teacher_inbox(update, context)
        return

    elif message_text == "👨‍🎓 Мої учні":
        students = db.get_teacher_students(user_id)
        if not students:
            await update.message.reply_text("У вас ще немає учнів.")
        else:
            text = "👨‍🎓 Мої учні:\n\n"
            for student in students:
                # Добавляем только эту проверку. Если данных нет — пропускаем итерацию.
                if not student:
                    continue
                
                # Используем .get или проверку на None для каждой строки, чтобы не вылетало
                first_name = student[2] if student[2] else "Учень"
                last_name = student[3] if student[3] else ""
                # Проверка индекса 6, чтобы бот не упал, если данных меньше
                language = student[6] if len(student) > 6 and student[6] else "Не вказано"
                
                text += f"👨‍🎓 {first_name} {last_name}\n"
                text += f"🗣 {language}\n\n"
                
            await update.message.reply_text(text)
        return
        
    elif message_text == "📚 Мої групи":
        await show_teacher_groups(update, context)
        return

    elif message_text == "👨‍💼 Керування користувачами":
        if user[4] == 'admin':
            keyboard = [
                [InlineKeyboardButton("👨‍🏫 Додати викладача", callback_data="add_teacher")],
                [InlineKeyboardButton("🔗 Призначити викладача", callback_data="assign_teacher")],
                [InlineKeyboardButton("🔄 Змінити викладача учня", callback_data="change_student_teacher")],
                [InlineKeyboardButton("📋 Список користувачів", callback_data="show_user_filters_menu")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ]
            await update.message.reply_text(
                "👨‍💼 Керування користувачами\n\nОберіть дію:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    elif message_text == "📊 Статистика":
        if user[4] == 'teacher':
            students_count = len(db.get_teacher_students(user_id))
            groups_count = len(db.get_teacher_groups(user_id))
            lessons_count = len(db.get_teacher_lessons(user_id))
            await update.message.reply_text(
                f"📊 Ваша статистика:\n\n"
                f"👥 Учнів: {students_count}\n"
                f"👥 Груп: {groups_count}\n"
                f"📚 Заплановано уроків: {lessons_count}"
            )
        return
    
   
    elif message_text == "📊 Звіти":
        if user[4] == 'admin':
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
        return
    
    # Перевірка тригерних слів
    for trigger in TRIGGER_WORDS:
        if trigger.lower() in message_text.lower():
            db.save_message(user_id, None, f"[TRIGGER: {trigger}] {message_text}", 'trigger')
    
    # Обробка створення групи
    if context.user_data.get('creating_group'):
        context.user_data['creating_group'] = False
        return await create_group_name(update, context)
    
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
    if context.user_data.get('waiting_for_admin_student_search') and user[4] == 'admin':
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
    if context.user_data.get('waiting_for_date') and user[4] == 'admin':
        try:
            date_obj = datetime.strptime(message_text.strip(), "%d.%m.%Y").date()
            date_str = date_obj.strftime('%Y-%m-%d')
            
            # Отримуємо всі повідомлення за дату
            # модальное окно
            conn = sqlite3.connect(db.db_name, timeout=30, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''SELECT m.*, u.first_name, u.last_name FROM messages m
                                JOIN users u ON m.from_user_id = u.user_id
                                WHERE date(m.timestamp) = ?
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
                        #if msg[3]: # Перевірка на group_id
                        if msg[4]: 
                            message_text = str(msg[4]) if msg[4] else ""
                        else:
                            message_text = str(msg[3]) if msg[3] else ""
                            
                        #это первич отрисовка окна после поиска по дате с данными (без сообщен)
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


# Якщо повідомлення не було кнопкою меню, не було командою в діалозі 
    # (наприклад, 'waiting_for_teacher_id' або 'waiting_for_date'),
    # і не було частиною активного чату (individual/group), 
    # то це довільний невідомий текст.
    
    # !!! ТУТ ЗАКІНЧУЄТЬСЯ ВАША ФУНКЦІЯ handle_message !!!

    # ДОДАЙТЕ ЦЕЙ БЛОК:
    
    if not context.user_data.get('chat_type'):
        # Це перевіряє, чи ми не знаходимося в активному чаті, і ловить довільний текст.
        # Викликаємо функцію-ловушку, яка повідомляє користувачу, що він написав не туди
        await fallback_message(update, context) 
        return


# === БЛОК ПОШУКУ КОРИСТУВАЧІВ ТА ГРУП ===
    if context.user_data.get('waiting_for_search_name'):
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
    # === КІНЕЦЬ БЛОКУ ПОШУКУ ===

async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text if update.message.text else "[Медіафайл]"
    
    # --- 1. ПЕРЕВІРКА НА ПОШУК (ДОДАЄМО ЦЕ) ---
    if context.user_data.get('waiting_for_search_name') and user_message != "[Медіафайл]":
        search_query = user_message.strip().lower()
        chat_type = context.user_data.get('search_chat_type', 'student')
        
        # Отримуємо користувачів
        users = db.get_users_by_role(chat_type)
        
        # Шукаємо збіги
        found_users = [
            u for u in users 
            if search_query in (u[2] or "").lower() or search_query in (u[3] or "").lower()
        ]
        
        if not found_users:
            await update.message.reply_text(
                f"❌ Нікого не знайдено за запитом '{user_message}'.\nСпробуйте інше ім'я або натисніть /start для скасування."
            )
            return # Зупиняємо функцію, щоб не спрацював "Вас ніхто не почув"

        # Формуємо список знайдених
        keyboard = []
        label = "👨‍🎓" if chat_type == "student" else "👨‍🏫"
        prefix = "view_chat_student" if chat_type == "student" else "view_chat_teacher"

        for u in found_users:
            name = f"{u[2] or ''} {u[3] or ''}".strip()
            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{u[0]}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад до списку", callback_data=f"chat_by_{chat_type}_0")])

        await update.message.reply_text(
            f"✅ Знайдено {len(found_users)} осіб за запитом '{user_message}':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Скидаємо прапорець очікування
        context.user_data['waiting_for_search_name'] = False
        return # Важливо! Виходимо, щоб далі не пішов текст про помилку
    # --- КІНЕЦЬ БЛОКУ ПОШУКУ ---

    # Далі йде ваш стандартний код...
    if user_message.startswith('/') and user_message != "[Медіафайл]":
        response_text = "❌ **Невідома команда.**\n\n"
    else:
        response_text = "👋 **Вас ніхто не почув.**\n\n"
        
    response_text += (
        "Щоб **написати викладачу** або виконати іншу дію, будь ласка, "
        "натисніть на **Меню (чотири квадратики)** ▣ у полі вводу та оберіть дію.\n\n"
        "Для швидкого зв'язку з адміністратором натисніть на **💬 Написати адміністратору**."
    )
    
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=IMAGE_WARNING_FILE_ID,
            caption=response_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Помилка при відправці фото: {e}")
        await update.message.reply_text(response_text, parse_mode='Markdown')


async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"File ID вашого фото: {file_id}")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        return

    chat_type = context.user_data.get('chat_type')
    
    # Визначаємо тип медіа просто для збереження в БД
    media_type = "media"
    if update.message.photo: media_type = "photo"
    elif update.message.document: media_type = "document"
    elif update.message.audio: media_type = "audio"
    elif update.message.video: media_type = "video"
    elif update.message.voice: media_type = "voice"

    caption = update.message.caption or ""
    sender_name = f"{user[2]} {user[3]}"

    # -------------------------
    # ІНДИВІДУАЛЬНИЙ ЧАТ (Викладач -> Учень)
    # -------------------------
    if chat_type == "individual" and "chat_with" in context.user_data:
        target_user_id = context.user_data["chat_with"]
        db.save_message(user_id, target_user_id, f"[{media_type}] {caption}", media_type)

        # Текст повідомлення, який піде ПІСЛЯ файлу
        notification_text = f"📎 Медіа від викладача {sender_name}"
        if caption:
            notification_text += f"\n\n{caption}"

        try:
            # 1. Надсилаємо сам файл БЕЗ підпису (копіюємо оригінал)
            await context.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
            # 2. Надсилаємо текст окремим повідомленням
            await context.bot.send_message(
                chat_id=target_user_id,
                text=notification_text
            )
            await update.message.reply_text("✅ Медіа відправлено")

        except Exception as e:
            print(f"❌ ERROR individual media: {e}")
            await update.message.reply_text(f"❌ Помилка відправки: {e}")

    # -------------------------
    # ГРУПОВИЙ ЧАТ (Викладач -> Група)
    # -------------------------
    elif chat_type == "group" and "chat_with_group" in context.user_data:
        group_id = context.user_data["chat_with_group"]
        members = db.get_group_members(group_id)
        group = next((g for g in db.get_all_groups() if g[0] == group_id), None)

        db.save_message(user_id, group_id=group_id, message_text=f"[{media_type}] {caption}", message_type=media_type)

        group_name = group[1] if group else ""
        notification_text = f"📎 Медіа в групу {group_name} від {sender_name}"
        if caption:
            notification_text += f"\n\n{caption}"

        recipients = [m[0] for m in members if m[0] != user_id]
        # Додаємо викладача групи, якщо це не той, хто надсилає зараз
        if group and group[2] not in recipients and group[2] != user_id:
            recipients.append(group[2])

        sent_count = 0
        for rec_id in recipients:
            try:
                # 1. Копіюємо файл
                await context.bot.copy_message(
                    chat_id=rec_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                # 2. Надсилаємо текст
                await context.bot.send_message(
                    chat_id=rec_id,
                    text=notification_text
                )
                sent_count += 1
            except Exception as e:
                print(f"DEBUG: Failed sending to {rec_id}: {e}")

        await update.message.reply_text(f"✅ Медіа відправлено {sent_count} учасникам")

    return


async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 📝 НОВИЙ ТЕКСТ ПОВІДОМЛЕННЯ-ПОПЕРЕДЖЕННЯ
    warning_message = (
        "Привіт! 👋"
        "\n\n Ваше повідомлення не потрапило до викладача."
        "\n ❗️Натисніть на **чотири квадратики** біля поля вводу → оберіть    **«💬 Написати викладачу/групі»** → виберіть групу та надішліть повідомлення ✉️"
    )
    
    chat_id = update.message.chat_id

    # Надсилаємо фото, використовуючи збережений file_id, та додаємо підпис
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=IMAGE_WARNING_FILE_ID, # Використовуємо ваш file_id
            caption=warning_message,
            parse_mode=ParseMode.MARKDOWN # Використовуємо ParseMode.MARKDOWN для жирного шрифту
        )
    except Exception as e:
        logger.error(f"Помилка надсилання фото-попередження: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Невідоме повідомлення! Будь ласка, використовуйте кнопки-підказки.",
            parse_mode=ParseMode.MARKDOWN
        )



async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Реєстрацію скасовано.")
    return ConversationHandler.END






async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    await update.message.reply_text(
        f"📋 Ваша інформація:\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Ім'я: {user.first_name}\n"
        f"👤 Прізвище: {user.last_name or 'Не вказано'}\n"
        f"📧 Username: @{user.username or 'Не вказано'}"
    )










# 3. ИСПРАВЛЕНИЕ: Обновленная функция main() с напоминаниями

async def handle_history_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_role = db.get_user(user_id)[4]

    if user_role == 'teacher':
        await show_teacher_chat_history(update, context, user_id)
    elif user_role == 'student':
        await show_student_chat_history(update, context, user_id)
    else:
        await update.message.reply_text("Ця функція доступна лише для викладачів та учнів.")







def main():
    application = Application.builder().token(BOT_TOKEN).build()

    init_super_admin()
    
    # Настроить автоматические напоминания
    schedule_daily_reminders(application)
    
    # Обробник розмови реєстрації
    registration_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_LANG: [CallbackQueryHandler(register_language), 
                           MessageHandler(filters.TEXT & ~filters.COMMAND, register_language)],
            REGISTER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_birthdate)],
            REGISTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_registration),
            CommandHandler('start', start)  # ДОДАЄМО СЮДИ: дозволяє переривати реєстрацію командою /start
        ],
        allow_reentry=True  # ДОДАЄМО СЮДИ: дозволяє заходити в розмову заново, навіть якщо вона не закінчена
    )
    
    # Обработник разговора добавления урока
    add_lesson_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^➕ Додати урок'), add_lesson_start)],
        states={
            ADD_LESSON_STUDENT: [CallbackQueryHandler(button_callback)],
            ADD_LESSON_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_date)],
            ADD_LESSON_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_lesson_time)],
        },
        fallbacks=[CommandHandler('cancel', cancel_add_lesson)],
    )

    # Обработник разговора создания группы
    create_group_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^create_group$")],
        states={
            CREATE_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_group_name)],
            CREATE_GROUP_TYPE: [CallbackQueryHandler(button_callback)],
            CREATE_GROUP_TEACHER: [CallbackQueryHandler(button_callback)],
            CREATE_GROUP_STUDENTS: [CallbackQueryHandler(button_callback)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern="^cancel_create_group$")],
    )

    # Обработник разговора сообщений преподавателя
    teacher_message_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^💬 Написати учневі/групі'), teacher_message_students),
            CallbackQueryHandler(teacher_quick_reply_start, pattern=r'^inbox_reply_\d+$'),
        ],
        states={
            TEACHER_MESSAGE_SELECT: [
                CallbackQueryHandler(button_callback)
            ],
            TEACHER_CHAT_ACTIVE: [
                MessageHandler(filters.Regex(r'^\s*Завершити діалог\s*🔚\s*$'), teacher_chat_end),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^Завершити діалог 🔚$'),
                    teacher_message_text
                ),
                MessageHandler(
                    filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
                    teacher_send_media
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(button_callback, pattern="^cancel_teacher_chat$"),
            CommandHandler('cancel', teacher_chat_end),
            CommandHandler('start', teacher_chat_end),  # /start скидає завислий діалог
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, teacher_chat_end),  # будь-яка кнопка меню теж скидає
        ],
        allow_reentry=True,  # дозволяє перезапустити діалог без зависання
    )



    # Обработник разговора массовой рассылки
    broadcast_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'.*Масова розсилка.*'), broadcast_start)
        ],
        states={
            # НОВИЙ СТАН: Вибір цілі
            BROADCAST_SELECT_TARGET: [
                CallbackQueryHandler(broadcast_select_target, pattern="^bc_target_"),
            ],
            
            BROADCAST_WAIT_MESSAGE: [
                # 1. Обробка медіа (перед текстом)
                MessageHandler(
                    filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE, 
                    broadcast_send_media
                ),
                # 2. Обробка тексту
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    broadcast_send_message
                ),
            ],
            # Додайте стан BROADCAST_SELECT_LIST, якщо хочете реалізувати "Списки"
        },
        fallbacks=[
            CallbackQueryHandler(broadcast_cancel, pattern="^cancel_broadcast$"),
            CommandHandler('cancel', broadcast_cancel),
        ],
    )


    # Обработник разговора сообщений ученика
    student_message_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^💬 Написати викладачеві/групі'), student_message_start),
            CallbackQueryHandler(quick_reply_start, pattern=r'^quick_reply_(teacher|group)_\d+$'),
        ],
        states={
            STUDENT_MESSAGE_SELECT: [
                CallbackQueryHandler(button_callback, pattern="^student_chat_"),
            ],
            STUDENT_CHAT_ACTIVE: [
                MessageHandler(filters.Regex(r'^\s*Завершити діалог\s*🔚\s*$'), student_chat_end),
                MessageHandler(
                    filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
                    student_send_media
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^Завершити діалог 🔚$'),
                    student_message_text
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(button_callback, pattern="^cancel_student_chat$"),
            CommandHandler('cancel', student_chat_end),
            CommandHandler('start', student_chat_end),  # /start скидає завислий діалог
            MessageHandler(MAIN_MENU_BUTTONS_FILTER, student_chat_end),  # будь-яка кнопка меню теж скидає
        ],
        allow_reentry=True,  # дозволяє перезапустити діалог без зависання
    )

 # ІСПРАВЛЕННЯ: Обробник админских уроков - додано точку входу для повторного додавання
    admin_lesson_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern="^admin_add_lesson_"),
            CallbackQueryHandler(button_callback, pattern="^admin_select_lesson_"),
            # НОВА ТОЧКА ВХОДУ: дозволяє кнопці "Додати ще" перезапустити діалог
            CallbackQueryHandler(button_callback, pattern="^admin_lesson_target_"),
            CallbackQueryHandler(button_callback, pattern="^admin_student_"),
            CallbackQueryHandler(button_callback, pattern="^admin_group_"),
        ],
        states={
            ADMIN_ADD_LESSON_DATE: [
                # 1. Спочатку перевіряємо, чи не натиснута кнопка скасування
                MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_admin_lesson),
                # 2. Якщо це не скасування, обробляємо як дату
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_lesson_date),
            ],
            ADMIN_ADD_LESSON_TIME: [
                # 1. Спочатку перевіряємо, чи не натиснута кнопка скасування
                MessageHandler(MAIN_MENU_BUTTONS_FILTER, cancel_admin_lesson),
                # 2. Якщо це не скасування, обробляємо як час
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_lesson_time),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_admin_lesson),
        ],
    )


    # Обработчики - ИСПРАВЛЕНИЕ: добавить admin_lesson_conv перед CallbackQueryHandler
    
    # Обробники
    # ===  ТИМЧАСОВИЙ ОБРОБНИК ДЛЯ ОТРИМАННЯ FILE_ID ===
    # *** ПІСЛЯ ОТРИМАННЯ ID ЙОГО ПОТРІБНО ВИДАЛИТИ ***
    #application.add_handler(MessageHandler(filters.PHOTO, get_file_id))
    application.add_handler(registration_conv)
    application.add_handler(add_lesson_conv)
    application.add_handler(create_group_conv)
    application.add_handler(teacher_message_conv)
    application.add_handler(admin_lesson_conv)
    application.add_handler(student_message_conv) 

    application.add_handler(broadcast_conv)

    application.add_handler(CommandHandler('admin', admin_command))
    application.add_handler(CommandHandler('manager', manager_command))
    application.add_handler(CommandHandler('teacher', teacher_command))
    # **ВАЖЛИВО:** Спеціалізовані обробники CallbackQueryHandler повинні йти перед універсальним
    application.add_handler(CallbackQueryHandler(show_user_filters_menu, pattern='^show_user_filters_menu$'))
    application.add_handler(CallbackQueryHandler(button_callback)) # Універсальний обробник має бути в кінці
    # Обробники повідомлень

    application.add_handler(CommandHandler('check_db', check_database_command))
    application.add_handler(CommandHandler('test_now', force_test_reminders))
    application.add_handler(CommandHandler("test_gs", test_gs))
    application.add_handler(CommandHandler('sync_students', sync_students_command))
    application.add_handler(CommandHandler('sync_teachers', sync_teachers_command))
    # -----------------------------------------------

    application.add_handler(MessageHandler(filters.Regex('^📖 Історія переписок$'), handle_history_button))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE, handle_media))
    # Обробники команд
    application.add_handler(CommandHandler('debug', debug_command))
    application.add_handler(CommandHandler('test_reminders', test_reminders_command))
    application.add_handler(CommandHandler('check_database', check_database_command))
    application.add_handler(CommandHandler('add_new_admin', make_admin_command))
    application.add_handler(CommandHandler('remove_admin', remove_admin_command))
    application.add_handler(CommandHandler('admin_list', admin_list_command))
    application.add_handler(CommandHandler('myid', myid_command))
    # **ВАЖЛИВО:** Цей рядок потрібно видалити, оскільки він викликав помилку NameError та дублює логіку

    # --------------------------
    # ДОДАТИ ОБРОБНИК РЕЗЕРВНОГО КОПІЮВАННЯ
    # --------------------------
    application.add_handler(CommandHandler("backup", backup_command))

# Обробник для невідомого ТЕКСТУ, який не є командою і не потрапив у жоден діалог.
    application.add_handler(
        MessageHandler(
            # Фільтр: Тільки текст, який не є командою.
            filters.TEXT & ~filters.COMMAND, 
            handle_unknown_text # <--- ВАША НОВА ФУНКЦІЯ З КАРТИНКОЮ
        )
    )



    print("🚀 Бот запущено...")
    print(f"👑 Головний адміністратор: ID {SUPER_ADMIN_ID}")
    print("📅 Автоматические напоминания об уроках настроены на 8:00")
    application.run_polling()

if __name__ == '__main__':
    main()