import asyncio
import html
from datetime import datetime
from multiprocessing import context
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from database.db_manager import db
from handlers.common import show_chat_page
from utils.keyboards import get_main_keyboard, get_chat_active_keyboard
from utils.helpers import is_lesson_link
from config.settings import TEACHER_CHAT_ACTIVE, STUDENT_CHAT_ACTIVE, STUDENT_MESSAGE_SELECT, TEACHER_MESSAGE_SELECT

_media_group_buffer: dict = {}


async def _flush_media_group(media_group_id: str, bot, recipients: list,
                             sender_label: str, save_callback,
                             reply_button: "InlineKeyboardMarkup | None" = None):
    """Чекає 1.2с після останнього файлу, потім відправляє весь альбом одним send_media_group."""
    await asyncio.sleep(1.2)

    entry = _media_group_buffer.pop(media_group_id, None)
    if not entry:
        return

    msgs = entry["messages"]
    if not msgs:
        return

    from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio

    media_items = []
    now_str = datetime.now().strftime("%d.%m %H:%M")
    header = f"{sender_label}  <i>{now_str}</i>"

    for i, msg in enumerate(msgs):
        user_caption = msg.caption or ""
        if i == 0:
            # Заголовок тільки на першому файлі, підпис якщо є
            cap = header + (f"\n\n{user_caption}" if user_caption else "")
            parse = 'HTML'
        else:
            # Наступні файли — без заголовку, тільки підпис якщо є
            cap = user_caption if user_caption else None
            parse = None

        if msg.photo:
            file_id = msg.photo[-1].file_id
            media_items.append(InputMediaPhoto(media=file_id, caption=cap, parse_mode=parse))
        elif msg.video:
            file_id = msg.video.file_id
            media_items.append(InputMediaVideo(media=file_id, caption=cap, parse_mode=parse))
        elif msg.document:
            file_id = msg.document.file_id
            media_items.append(InputMediaDocument(media=file_id, caption=cap, parse_mode=parse))
        elif msg.audio:
            file_id = msg.audio.file_id
            media_items.append(InputMediaAudio(media=file_id, caption=cap, parse_mode=parse))

    if not media_items:
        return

    for r_id in recipients:
        try:
            if len(media_items) == 1:
                # Одиночний файл — caption і кнопка прямо в copy_message
                await bot.copy_message(
                    chat_id=r_id,
                    from_chat_id=msgs[0].chat.id,
                    message_id=msgs[0].message_id,
                    caption=header + (f"\n\n{msgs[0].caption}" if msgs[0].caption else ""),
                    parse_mode='HTML',
                    reply_markup=reply_button
                )
            else:
                # Альбом — send_media_group (без reply_markup, Telegram не підтримує)
                await bot.send_media_group(chat_id=r_id, media=media_items)
                # Кнопка окремим повідомленням після альбому
                if reply_button:
                    await bot.send_message(
                        chat_id=r_id,
                        text="⬆️ Альбом вище",
                        reply_markup=reply_button
                    )
        except Exception as e:
            print(f"[MediaGroup] error to {r_id}: {e}")

    if save_callback:
        try:
            save_callback(len(media_items))
        except Exception as e:
            print(f"[MediaGroup] save error: {e}")

    # Одне підтвердження відправнику на весь альбом
    try:
        sender_chat_id = entry.get("sender_chat_id")
        target_label = entry.get("target_label", "")
        if sender_chat_id:
            n = len(media_items)
            word = "файли" if n > 1 else "файл"
            await bot.send_message(
                chat_id=sender_chat_id,
                text=f"✅ Альбом ({n} {word}) відправлено {target_label}."
            )
    except Exception as e:
        print(f"[MediaGroup] confirm error: {e}")


async def student_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает список преподавателей и групп, доступных для чата ученику."""
    user_id = update.effective_user.id

    teacher = db.get_student_teacher(user_id)
    groups = db.get_student_groups(user_id)

    keyboard = []

    if teacher:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🏫 {teacher[2]} {teacher[3]}",
            callback_data=f"student_chat_teacher_{teacher[0]}"
        )])
        context.user_data['student_teacher_id'] = teacher[0]

    if groups:
        for group in groups:
            keyboard.append([InlineKeyboardButton(
                f"👥 Група '{group[1]}'",
                callback_data=f"student_chat_group_{group[0]}"
            )])

    if not teacher and not groups:
        await update.message.reply_text("На жаль, у вас немає призначеного викладача або групи для початку діалогу.")
        return ConversationHandler.END

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_student_chat")])

    await update.message.reply_text(
        "Оберіть співрозмовника:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return STUDENT_MESSAGE_SELECT


async def student_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    print(f"--- STUDENT_CHAT DEBUG ---")
    print(f"Text: {update.message.text}")
    print(f"Caption: {update.message.caption}")
    print(f"Has Photo: {bool(update.message.photo)}")
    print(f"--------------------------")
    # ===================
    # 1. Визначаємо вміст повідомлення
    # Якщо є медіа (фото, документ, відео), текст знаходиться в .caption, інакше в .text
    message_caption = update.message.caption
    message_text = update.message.text

    # Визначаємо, чи містить повідомлення медіафайл
    is_media = update.message.photo or update.message.document or update.message.video or update.message.animation

    if is_media:
        # Для медіа використовуємо підпис
        content_text = message_caption if message_caption else ""
    else:
        # Для чистого тексту використовуємо message_text
        content_text = message_text

    # Захист від порожнього повідомлення (якщо немає тексту і немає медіа)
    if not content_text and not is_media:
        await update.message.reply_text("❌ Повідомлення не може бути пустим.")
        return STUDENT_CHAT_ACTIVE

    # Отримання даних учня
    student_id = update.effective_user.id
    student = db.get_user(student_id)
    student_full_name = f"{student[2]} {student[3]}" if student else "Невідомий учень"

    chat_type = context.user_data.get('student_chat_type')

    # === ГІЛКА 1: ІНДИВІДУАЛЬНИЙ ЧАТ З ВИКЛАДАЧЕМ ===
    if chat_type == 'individual':
        target_teacher_id = context.user_data.get('student_chat_with')
        safe_content = content_text.strip() if content_text else ""

        # Компактне сповіщення без повторюваної інструкції
        now_str = datetime.now().strftime("%d.%m %H:%M")
        notification_text = (
            f"📩 <b>{student_full_name}</b>  <i>{now_str}</i>\n\n"
            f"{safe_content}"
        )

        # Кнопка "Відповісти" прямо під повідомленням
        quick_reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти {student_full_name.split()[0]}",
                callback_data=f"inbox_reply_{student_id}"
            )
        ]])

        # Зберігаємо повідомлення в БД
        db.save_message(student_id, target_teacher_id, content_text, message_type='media' if is_media else 'text')

        try:
            if is_media:
                await context.bot.copy_message(
                    chat_id=target_teacher_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                await context.bot.send_message(
                    chat_id=target_teacher_id,
                    text=notification_text,
                    parse_mode='HTML',
                    reply_markup=quick_reply_markup
                )
            else:
                await context.bot.send_message(
                    target_teacher_id,
                    notification_text,
                    parse_mode='HTML',
                    reply_markup=quick_reply_markup
                )

            await update.message.reply_text("✅ Повідомлення відправлено.")
        except Exception:
            await update.message.reply_text("❌ Не вдалося відправити повідомлення. Спробуйте пізніше.")

    # === ГІЛКА 2: ЧАТ З ГРУПОЮ ===
    elif chat_type == 'group':
        group_id = context.user_data.get('student_chat_with_group')
        group_info = db.get_group_by_id(group_id)
        members = db.get_group_members(group_id)

        if group_info:
            group_name = group_info[1]
            teacher_id = group_info[2]
            now_str = datetime.now().strftime("%d.%m %H:%M")

            # Компактне сповіщення для групи
            notification_text = (
                f"👥 <b>{group_name}</b> · <b>{student_full_name}</b>  <i>{now_str}</i>\n\n"
                f"{content_text}"
            )

            # Зберігаємо в базу
            db.save_message(student_id, to_user_id=teacher_id, group_id=group_id,
                            message_text=content_text, message_type='media' if is_media else 'text')

            # Збираємо унікальний список отримувачів (учні + викладач)
            recipients = set()
            for m in members:
                recipients.add(m[0])
            if teacher_id:
                recipients.add(teacher_id)
            if student_id in recipients:
                recipients.remove(student_id)

            # Розсилка всім у циклі
            sent_count = 0
            for target_id in recipients:
                try:
                    if is_media:
                        await context.bot.copy_message(
                            chat_id=target_id,
                            from_chat_id=update.effective_chat.id,
                            message_id=update.message.message_id
                        )
                        await context.bot.send_message(
                            chat_id=target_id,
                            text=notification_text,
                            parse_mode='HTML'
                        )
                    else:
                        await context.bot.send_message(
                            target_id,
                            notification_text,
                            parse_mode='HTML'
                        )
                    sent_count += 1
                except Exception as e:
                    print(f"Помилка відправки до {target_id}: {e}")

            await update.message.reply_text(f"✅ Повідомлення відправлено учасникам групи ({sent_count}).")
        else:
            await update.message.reply_text("❌ Не вдалося знайти інформацію про групу.")

    return STUDENT_CHAT_ACTIVE


async def student_chat_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершує активний діалог і повертає основне меню для учня."""
    context.user_data.pop('student_chat_type', None)
    context.user_data.pop('student_chat_with', None)
    context.user_data.pop('student_chat_with_group', None)

    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("Помилка: користувача не знайдено.")
        return ConversationHandler.END

    role = user[4]

    # Якщо це /start або /cancel — не надсилаємо зайве повідомлення, start сам покаже меню
    command = update.message.text.strip() if update.message and update.message.text else ""
    if command in ('/start', '/cancel'):
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Діалог завершено. Ви повернулися до головного меню.",
        reply_markup=get_main_keyboard(role)
    )
    return ConversationHandler.END


async def student_send_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    student_id = update.effective_user.id
    student = db.get_user(student_id)
    student_full_name = f"{student[2]} {student[3]}" if student else "Невідомий учень"
    chat_type = context.user_data.get('student_chat_type')

    # --- Визначення отримувачів ---
    recipients = set()
    group_id_for_db = None
    target_teacher_id = None
    target_label = "викладачеві"

    if chat_type == 'individual':
        target_teacher_id = context.user_data.get('student_chat_with')
        if target_teacher_id:
            recipients.add(target_teacher_id)
        target_label = "викладачеві"

    elif chat_type == 'group':
        gid = context.user_data.get('student_chat_with_group')
        group_info = db.get_group_by_id(gid)
        if not group_info:
            if not update.message.media_group_id:
                await update.message.reply_text("❌ Групу не знайдено.")
            return STUDENT_CHAT_ACTIVE
        group_id_for_db = gid
        target_teacher_id = group_info[2]
        members = db.get_group_members(gid)
        for m in members:
            recipients.add(m[0])
        if target_teacher_id:
            recipients.add(target_teacher_id)
        target_label = f"групі '{group_info[1]}'"

    recipients.discard(student_id)

    if not recipients:
        if not update.message.media_group_id:
            await update.message.reply_text("❌ Не вдалося визначити отримувача.")
        return STUDENT_CHAT_ACTIVE

    # Заголовок повідомлення
    if chat_type == 'group':
        gid = context.user_data.get('student_chat_with_group')
        group_info = db.get_group_by_id(gid)
        gname = group_info[1] if group_info else ""
        sender_label = f"👥 <b>{gname}</b> · <b>{student_full_name}</b>"
    else:
        sender_label = f"📩 <b>{student_full_name}</b>"

    # --- Якщо це частина альбому — буферизуємо ---
    mgid = update.message.media_group_id
    if mgid:
        def save_cb(count):
            db.save_message(
                student_id,
                to_user_id=target_teacher_id,
                group_id=group_id_for_db,
                message_text=f"[АЛЬБОМ {count} файлів]",
                message_type='media'
            )

        # Кнопка відповіді для альбому
        if chat_type == 'individual':
            album_reply_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"↩️ Відповісти {student_full_name.split()[0]}",
                    callback_data=f"quick_reply_teacher_{context.user_data.get('student_chat_with')}"
                )
            ]])
        else:
            gid_btn = context.user_data.get('student_chat_with_group')
            ginfo_btn = db.get_group_by_id(gid_btn)
            gname_btn = ginfo_btn[1] if ginfo_btn else "групу"
            album_reply_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"↩️ Відповісти в групу {gname_btn}",
                    callback_data=f"quick_reply_group_{gid_btn}"
                )
            ]])

        if mgid not in _media_group_buffer:
            _media_group_buffer[mgid] = {
                "messages": [],
                "sender_chat_id": update.effective_chat.id,
                "target_label": target_label,
                "task": None
            }

        _media_group_buffer[mgid]["messages"].append(update.message)

        old_task = _media_group_buffer[mgid].get("task")
        if old_task and not old_task.done():
            old_task.cancel()

        task = asyncio.ensure_future(
            _flush_media_group(mgid, context.bot, list(recipients),
                               sender_label, save_cb, reply_button=album_reply_btn)
        )
        _media_group_buffer[mgid]["task"] = task
        return STUDENT_CHAT_ACTIVE

    # --- Одиночний файл — відправляємо одразу ---
    # Визначаємо file_id та тип медіа
    msg = update.message
    if msg.photo:
        media_file_id = msg.photo[-1].file_id
        media_type = 'photo'
    elif msg.document:
        media_file_id = msg.document.file_id
        media_type = 'document'
    elif msg.audio:
        media_file_id = msg.audio.file_id
        media_type = 'audio'
    elif msg.video:
        media_file_id = msg.video.file_id
        media_type = 'video'
    elif msg.voice:
        media_file_id = msg.voice.file_id
        media_type = 'voice'
    else:
        media_file_id = None
        media_type = 'media'

    def save_single(_=None):
        db.save_message(
            student_id,
            to_user_id=target_teacher_id,
            group_id=group_id_for_db,
            message_text=update.message.caption or '',
            message_type=media_type,
            file_id=media_file_id
        )

    now_str = datetime.now().strftime("%d.%m %H:%M")
    # Заголовок йде як підпис прямо на фото/файл — без окремого повідомлення
    header = f"{sender_label}  <i>{now_str}</i>"
    user_caption = update.message.caption or ""
    new_caption = header + (f"\n\n{user_caption}" if user_caption else "")

    # Кнопка "Відповісти" залежно від типу чату
    if chat_type == 'individual':
        target_teacher_id_for_btn = context.user_data.get('student_chat_with')
        r_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти {student_full_name.split()[0]}",
                callback_data=f"quick_reply_teacher_{target_teacher_id_for_btn}"
            )
        ]])
    else:
        gid_btn = context.user_data.get('student_chat_with_group')
        group_info_btn = db.get_group_by_id(gid_btn)
        gname_btn = group_info_btn[1] if group_info_btn else "групу"
        r_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти в групу {gname_btn}",
                callback_data=f"quick_reply_group_{gid_btn}"
            )
        ]])

    sent_count = 0
    for r_id in recipients:
        try:
            await context.bot.copy_message(
                chat_id=r_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                caption=new_caption,
                parse_mode='HTML',
                reply_markup=r_markup
            )
            sent_count += 1
        except Exception as e:
            print(f"student_send_media single error to {r_id}: {e}")

    save_single()
    await update.message.reply_text(f"✅ Файл відправлено {target_label}.")
    return STUDENT_CHAT_ACTIVE


async def teacher_quick_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входу для викладача через кнопку ↩️ Відповісти у Вхідніх."""
    query = update.callback_query
    await query.answer()

    teacher_id = query.from_user.id
    student_id = int(query.data.split("_")[2])  # inbox_reply_<student_id>

    student = db.get_user(student_id)
    if not student:
        await query.answer("❌ Учня не знайдено.", show_alert=True)
        return ConversationHandler.END

    student_name = f"{student[2]} {student[3]}"

    # Позначаємо прочитаним
    db.mark_messages_read(from_user_id=student_id, to_user_id=teacher_id)

    context.user_data['teacher_chat_with'] = student_id
    context.user_data['teacher_chat_type'] = 'individual'

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        teacher_id,
        f"✏️ Відповідь для <b>{student_name}</b>.\nНапишіть повідомлення:",
        parse_mode='HTML',
        reply_markup=get_chat_active_keyboard()
    )
    return TEACHER_CHAT_ACTIVE


async def quick_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входу для швидкої відповіді учня через кнопку під повідомленням.
    callback_data формат:
      quick_reply_teacher_<teacher_id>
      quick_reply_group_<group_id>
    """
    query = update.callback_query
    await query.answer()

    student_id = query.from_user.id
    data = query.data  # напр. "quick_reply_teacher_12345"

    parts = data.split("_")  # ['quick', 'reply', 'teacher', '12345']
    reply_type = parts[2]  # 'teacher' або 'group'
    target_id = int(parts[3])

    if reply_type == "teacher":
        teacher = db.get_user(target_id)
        if not teacher:
            await query.answer("❌ Викладача не знайдено.", show_alert=True)
            return ConversationHandler.END

        context.user_data['student_chat_with'] = target_id
        context.user_data['student_chat_type'] = 'individual'

        teacher_name = f"{teacher[2]} {teacher[3]}"
        await query.edit_message_reply_markup(reply_markup=None)  # прибираємо кнопку
        await context.bot.send_message(
            student_id,
            f"✏️ Відповідь для <b>{teacher_name}</b>.\nНапишіть повідомлення:",
            parse_mode='HTML',
            reply_markup=get_chat_active_keyboard()
        )

    elif reply_type == "group":
        group_info = db.get_group_by_id(target_id)
        if not group_info:
            await query.answer("❌ Групу не знайдено.", show_alert=True)
            return ConversationHandler.END

        context.user_data['student_chat_with_group'] = target_id
        context.user_data['student_chat_type'] = 'group'

        group_name = group_info[1]
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            student_id,
            f"✏️ Відповідь у групу <b>{group_name}</b>.\nНапишіть повідомлення:",
            parse_mode='HTML',
            reply_markup=get_chat_active_keyboard()
        )

    return STUDENT_CHAT_ACTIVE


async def teacher_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # === ДІАГНОСТИКА ===
    print(f"--- TEACHER_CHAT DEBUG ---")
    print(f"Text: {update.message.text}")
    print(f"Caption: {update.message.caption}")
    print(f"Has Photo: {bool(update.message.photo)}")
    print(f"--------------------------")
    # ===================
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    teacher_full_name = f"{user[2]} {user[3]}"
    message_text = update.message.text

    # === НОВА ІНСТРУКЦІЯ ДЛЯ УЧНЯ ===
    # (інструкція більше не вставляється в кожне повідомлення)

    # 🐞 DEBUG 1: Начало функции
    print(f"DEBUG 1: teacher_message_text started. Sender ID: {user_id}. Message: '{message_text[:30]}...'")

    chat_type = context.user_data.get('teacher_chat_type')

    if chat_type == 'individual':
        target_student_id = context.user_data.get('teacher_chat_with')
        target_student = db.get_user(target_student_id)

        # 🐞 DEBUG 2: Индивидуальный чат
        print(f"DEBUG 2: Chat Type: Individual. Target ID: {target_student_id}")

        # Зберегти повідомлення
        db.save_message(user_id, target_student_id, message_text)

        now_str = datetime.now().strftime("%d.%m %H:%M")
        # Компактне сповіщення учню
        student_notification = (
            f"📩 <b>{teacher_full_name}</b>  <i>{now_str}</i>\n\n"
            f"{message_text}"
        )

        # Кнопка "Відповісти" прямо під повідомленням
        student_reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"↩️ Відповісти {teacher_full_name.split()[0]}",
                callback_data=f"quick_reply_teacher_{user_id}"
            )
        ]])

        # Відправити повідомлення
        try:
            # 1. Надсилаємо повідомлення і зберігаємо результат у змінну sent_msg
            sent_msg = await context.bot.send_message(
                target_student_id,
                student_notification,
                parse_mode='HTML',
                reply_markup=student_reply_markup
            )

            # --- НОВИЙ БЛОК: ЗАКРІПЛЕННЯ ---
            if is_lesson_link(message_text):
                try:
                    await context.bot.pin_chat_message(
                        chat_id=target_student_id,
                        message_id=sent_msg.message_id,
                        disable_notification=True
                    )
                    print(f"DEBUG: Lesson link pinned for student {target_student_id}")
                except Exception as pin_err:
                    print(f"DEBUG: Failed to pin message: {pin_err}")
            # ------------------------------

            await update.message.reply_text("✅ Повідомлення відправлено")
            print(f"DEBUG 3: Message successfully sent to student {target_student_id}")

        except Exception as e:
            print(f"DEBUG 4: ERROR sending message to student {target_student_id}: {e}")
            await update.message.reply_text("❌ Не вдалося відправити повідомлення. Можливо, учень заблокував бота.")

    elif chat_type == 'group':
        group_id = context.user_data.get('teacher_chat_with_group')
        members = db.get_group_members(group_id)
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)

        if not group:
            await update.message.reply_text("❌ Помилка: групу не знайдено.")
            return TEACHER_CHAT_ACTIVE

        group_name = group[1]

        # 🐞 DEBUG 2: Групповой чат
        print(f"DEBUG 2: Chat Type: Group. Target Group ID: {group_id}. Members count: {len(members)}")

        # Зберегти повідомлення
        db.save_message(user_id, group_id=group_id, message_text=message_text)

        now_str = datetime.now().strftime("%d.%m %H:%M")
        # Компактне сповіщення групі
        group_notification = (
            f"👥 <b>{group_name}</b> · <b>{teacher_full_name}</b>  <i>{now_str}</i>\n\n"
            f"{message_text}"
        )

        # Відправити всім учасникам групи
        sent_count = 0
        for member in members:
            # ПЕРЕВІРКА: не надсилати самому собі (викладачу)
            if member[0] == user_id:
                continue

            # Кнопка "Відповісти в групу" для кожного учасника
            member_reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"↩️ Відповісти в групу {group_name}",
                    callback_data=f"quick_reply_group_{group_id}"
                )
            ]])

            try:
                # 1. Надсилаємо повідомлення
                sent_msg = await context.bot.send_message(
                    member[0],
                    group_notification,
                    parse_mode='HTML',
                    reply_markup=member_reply_markup
                )

                # --- НОВИЙ БЛОК: ЗАКРІПЛЕННЯ У ГРУПІ ---
                if is_lesson_link(message_text):
                    try:
                        await context.bot.pin_chat_message(
                            chat_id=member[0],
                            message_id=sent_msg.message_id,
                            disable_notification=True
                        )
                    except Exception as pin_err:
                        print(f"DEBUG: Failed to pin in group for {member[0]}: {pin_err}")
                # --------------------------------------

                sent_count += 1
            except Exception as e:
                print(f"Помилка відправки учню {member[0]}: {e}")

        await update.message.reply_text(f"✅ Повідомлення відправлено {sent_count} учасникам групи")

        # 🐞 DEBUG 3: Отправка успешна
        print(f"DEBUG 3: Message successfully sent to {sent_count} members of group {group_id}")

    # 🐞 DEBUG 5: Возврат состояния
    print(f"DEBUG 5: Returning state TEACHER_CHAT_ACTIVE")
    return TEACHER_CHAT_ACTIVE


async def teacher_chat_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает активный диалог и возвращает основное меню."""
    print("--- DEBUG: teacher_chat_end ВИКЛИКАНО! ---")

    context.user_data.pop('teacher_chat_type', None)
    context.user_data.pop('teacher_chat_with', None)
    context.user_data.pop('teacher_chat_with_group', None)

    user_id = update.effective_user.id
    user = db.get_user(user_id)
    role = user[4]

    # Якщо це /start — не надсилаємо "Діалог завершено", бо start сам покаже меню
    command = update.message.text.strip() if update.message and update.message.text else ""
    if command in ('/start', '/cancel'):
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Діалог завершено. Ви повернулися до головного меню.",
        reply_markup=get_main_keyboard(role)
    )
    return ConversationHandler.END


async def teacher_message_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user or user[4] != 'teacher':
        await update.message.reply_text("Ця функція доступна лише викладачам.")
        return

    # Отримати індивідуальних учнів
    students = db.get_teacher_students(user_id)
    # Отримати групи
    groups = db.get_teacher_groups(user_id)

    if not students and not groups:
        await update.message.reply_text("У вас ще немає учнів та груп.")
        return

    keyboard = []

    for student in students:
        keyboard.append([InlineKeyboardButton(
            f"👨‍🎓 {student[2]} {student[3]} (індивідуально)",
            callback_data=f"teacher_chat_student_{student[0]}"
        )])

    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"👥 {group[1]} ({group[3]})",
            callback_data=f"teacher_chat_group_{group[0]}"
        )])

    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_teacher_chat")])

    await update.message.reply_text(
        "💬 Кому хочете написати?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TEACHER_MESSAGE_SELECT


async def teacher_send_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка медіафайлів від викладача — з підтримкою альбомів."""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    teacher_full_name = f"{user[2]} {user[3]}"
    chat_type = context.user_data.get('teacher_chat_type')

    # --- Визначення отримувачів ---
    recipients = set()
    group_id_for_db = None
    target_label = "учню"

    if chat_type == 'individual':
        target_student_id = context.user_data.get('teacher_chat_with')
        if target_student_id:
            recipients.add(target_student_id)
            student = db.get_user(target_student_id)
            if student:
                target_label = f"{student[2]} {student[3]}"

    elif chat_type == 'group':
        gid = context.user_data.get('teacher_chat_with_group')
        group_info = db.get_group_by_id(gid)
        if not group_info:
            if not update.message.media_group_id:
                await update.message.reply_text("❌ Групу не знайдено.")
            return TEACHER_CHAT_ACTIVE
        group_id_for_db = gid
        members = db.get_group_members(gid)
        for m in members:
            if m[0] != user_id:
                recipients.add(m[0])
        target_label = f"групі '{group_info[1]}'"

    if not recipients:
        if not update.message.media_group_id:
            await update.message.reply_text("❌ Не вдалося визначити отримувача.")
        return TEACHER_CHAT_ACTIVE

    # Заголовок
    if chat_type == 'group':
        gid = context.user_data.get('teacher_chat_with_group')
        group_info = db.get_group_by_id(gid)
        gname = group_info[1] if group_info else ""
        sender_label = f"👥 <b>{html.escape(gname)}</b> · <b>{html.escape(teacher_full_name)}</b>"
    else:
        sender_label = f"📩 <b>{html.escape(teacher_full_name)}</b>"

    # --- Якщо це частина альбому — буферизуємо ---
    mgid = update.message.media_group_id
    if mgid:
        def save_cb(count):
            db.save_message(
                user_id,
                to_user_id=context.user_data.get('teacher_chat_with') if chat_type == 'individual' else None,
                group_id=group_id_for_db,
                message_text=f"[АЛЬБОМ {count} файлів]",
                message_type='media'
            )

        # Кнопка відповіді для альбому
        if chat_type == 'individual':
            album_reply_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"↩️ Відповісти {teacher_full_name.split()[0]}",
                    callback_data=f"quick_reply_teacher_{user_id}"
                )
            ]])
        else:
            gid_btn = context.user_data.get('teacher_chat_with_group')
            ginfo_btn = db.get_group_by_id(gid_btn)
            gname_btn = ginfo_btn[1] if ginfo_btn else "групу"
            album_reply_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"↩️ Відповісти в групу {gname_btn}",
                    callback_data=f"quick_reply_group_{gid_btn}"
                )
            ]])

        if mgid not in _media_group_buffer:
            _media_group_buffer[mgid] = {
                "messages": [],
                "sender_chat_id": update.effective_chat.id,
                "target_label": target_label,
                "task": None
            }

        _media_group_buffer[mgid]["messages"].append(update.message)

        old_task = _media_group_buffer[mgid].get("task")
        if old_task and not old_task.done():
            old_task.cancel()

        task = asyncio.ensure_future(
            _flush_media_group(mgid, context.bot, list(recipients),
                               sender_label, save_cb, reply_button=album_reply_btn)
        )
        _media_group_buffer[mgid]["task"] = task
        return TEACHER_CHAT_ACTIVE

    # --- Одиночний файл ---
    now_str = datetime.now().strftime("%d.%m %H:%M")
    user_caption = update.message.caption or ""
    new_caption = (
            f"{sender_label}  <i>{now_str}</i>"
            + (f"\n\n{html.escape(user_caption)}" if user_caption else "")
    )

    # Визначаємо file_id та тип медіа
    msg = update.message
    if msg.photo:
        t_file_id = msg.photo[-1].file_id
        t_media_type = 'photo'
    elif msg.document:
        t_file_id = msg.document.file_id
        t_media_type = 'document'
    elif msg.audio:
        t_file_id = msg.audio.file_id
        t_media_type = 'audio'
    elif msg.video:
        t_file_id = msg.video.file_id
        t_media_type = 'video'
    elif msg.voice:
        t_file_id = msg.voice.file_id
        t_media_type = 'voice'
    else:
        t_file_id = None
        t_media_type = 'media'

    db.save_message(
        user_id,
        to_user_id=context.user_data.get('teacher_chat_with') if chat_type == 'individual' else None,
        group_id=group_id_for_db,
        message_text=user_caption,
        message_type=t_media_type,
        file_id=t_file_id
    )

    sent_count = 0
    for r_id in recipients:
        try:
            if chat_type == 'individual':
                r_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"↩️ Відповісти {teacher_full_name.split()[0]}",
                        callback_data=f"quick_reply_teacher_{user_id}"
                    )
                ]])
            else:
                gid = context.user_data.get('teacher_chat_with_group')
                group_info_btn = db.get_group_by_id(gid)
                gname = group_info_btn[1] if group_info_btn else "групу"
                r_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"↩️ Відповісти в групу {gname}",
                        callback_data=f"quick_reply_group_{gid}"
                    )
                ]])
            # caption і reply_markup одразу в copy_message — без окремого send_message
            await context.bot.copy_message(
                chat_id=r_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                caption=new_caption,
                parse_mode='HTML',
                reply_markup=r_markup
            )
            sent_count += 1
        except Exception as e:
            print(f"teacher_send_media single error to {r_id}: {e}")

    await update.message.reply_text(f"✅ Файл відправлено {target_label}.")
    return TEACHER_CHAT_ACTIVE


async def teacher_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Функція для викладача: відправка тексту та медіа учневі або групі.
    Виправлено за логікою учня: медіа та текст окремо, щоб уникнути помилок довжини caption.
    """
    user_id = update.effective_user.id
    teacher = db.get_user(user_id)
    if not teacher:
        await update.message.reply_text("❌ Помилка: Вас не знайдено в базі даних.")
        return TEACHER_CHAT_ACTIVE

    teacher_full_name = f"{teacher[2]} {teacher[3]}"
    chat_type = context.user_data.get('chat_type')

    # Отримуємо текст повідомлення
    message_text = update.message.text or update.message.caption or ""
    is_media = bool(update.message.photo or update.message.video or update.message.document or update.message.voice)

    # 1. Визначення цілі
    target_user_id = None
    group_id = None
    group_name = "Невідома група"

    if chat_type == 'individual':
        target_user_id = context.user_data.get('chat_with')
        if not target_user_id:
            await update.message.reply_text("❌ Не обрано учня для чату.")
            return TEACHER_CHAT_ACTIVE
    elif chat_type == 'group':
        group_id = context.user_data.get('chat_with_group')
        group_info = db.get_group_by_id(group_id)
        if group_info:
            group_name = group_info[1]
        else:
            await update.message.reply_text("❌ Групу не знайдено.")
            return TEACHER_CHAT_ACTIVE

    # 2. Формування тексту повідомлення
    if chat_type == 'individual':
        notification_text = f"🎓 Повідомлення від викладача {teacher_full_name}:\n\n"
    else:
        notification_text = f"👥 Повідомлення в групу '{group_name}' від викладача {teacher_full_name}:\n\n"

    if message_text:
        notification_text += message_text

    # 3. Зберігання в БД
    db.save_message(
        user_id,
        to_user_id=target_user_id if chat_type == 'individual' else None,
        group_id=group_id if chat_type == 'group' else None,
        message_text=message_text if not is_media else f"[МЕДІА] {message_text}",
        message_type='media' if is_media else 'text'
    )

    # 4. Список отримувачів
    recipients = set()
    if chat_type == 'individual':
        recipients.add(target_user_id)
    else:
        members = db.get_group_members(group_id)
        for m in members:
            recipients.add(m[0])
        group_info = db.get_group_by_id(group_id)
        if group_info and group_info[2]:
            recipients.add(group_info[2])

    recipients.discard(user_id)

    # 5. Відправка
    sent_count = 0
    for r_id in recipients:
        try:
            if is_media:
                # Копіюємо медіа
                await context.bot.copy_message(
                    chat_id=r_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    # МИ НЕ ПЕРЕДАЄМО ТУТ CAPTION, щоб не було помилок
                )
                # Надсилаємо текст окремо
                await context.bot.send_message(
                    chat_id=r_id,
                    text=notification_text,
                    parse_mode=None  # ЯВНО ВИМИКАЄМО ПАРСИНГ (це вирішить проблему з '_')
                )
            else:
                # Якщо просто текст
                await context.bot.send_message(
                    chat_id=r_id,
                    text=notification_text,
                    parse_mode=None  # ЯВНО ВИМИКАЄМО ПАРСИНГ
                )
            sent_count += 1
        except Exception as e:
            # Виводимо повну помилку в консоль, щоб ви бачили, що саме не так
            print(f"Помилка відправки викладачем до {r_id}: {e}")

    # 6. Звіт
    if chat_type == 'group':
        await update.message.reply_text(f"✅ Відправлено учасникам групи ({sent_count}).")
    else:
        await update.message.reply_text("✅ Повідомлення відправлено учневі.")

    return TEACHER_CHAT_ACTIVE


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        return

    chat_type = context.user_data.get('chat_type')

    # Визначаємо тип медіа просто для збереження в БД
    media_type = "media"
    if update.message.photo:
        media_type = "photo"
    elif update.message.document:
        media_type = "document"
    elif update.message.audio:
        media_type = "audio"
    elif update.message.video:
        media_type = "video"
    elif update.message.voice:
        media_type = "voice"

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


async def chat_engine_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    # Отримуємо роль користувача
    user = db.get_user(user_id)
    user_role = user[4] if user else 'student'
    
    print(f"DEBUG: Callback data received: {data} | User Role: {user_role}")

    # 1. --- СТАРТ НОВОГО ЧАТУ (Запис повідомлення) ---
    if data.startswith("chat_teacher_") or data.startswith("chat_group_"):
        parts = data.split("_")
        target_id = int(parts[2])
        
        if data.startswith("chat_teacher_"):
            context.user_data['chat_with'] = target_id
            context.user_data['chat_type'] = 'individual'
            target = db.get_user(target_id)
            name = f"{target[2]} {target[3]}"
        else:
            context.user_data['chat_with_group'] = target_id
            context.user_data['chat_type'] = 'group'
            group = db.get_group_by_id(target_id)
            name = group[1]

        await query.edit_message_text(f"💬 Чат з {name}\n\nНапишіть ваше повідомлення:")
        return

    # 2. --- ПЕРЕГЛЯД СПИСКУ (Кого дивимось: учні/вчителі/групи) ---
    elif data.startswith("chat_by_"):
        parts = data.split("_")
        chat_type = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        items_per_page = 10

        if chat_type == "student":
            users = db.get_users_by_role('student')
            users.sort(key=lambda x: (x[2] or "").lower())
            label, prefix, title = "👨‍🎓", "view_chat_student", "Оберіть учня:"
        elif chat_type == "teacher":
            users = db.get_users_by_role('teacher')
            users.sort(key=lambda x: (x[2] or "").lower())
            label, prefix, title = "👨‍🏫", "view_chat_teacher", "Оберіть викладача:"
        elif chat_type == "group":
            users = db.get_all_groups()
            label, prefix, title = "👥", "view_chat_group", "Оберіть групу:"
        else: return

        if not users:
            await query.edit_message_text(f"Немає даних для {chat_type}.")
            return

        total_pages = (len(users) + items_per_page - 1) // items_per_page
        start, end = page * items_per_page, (page + 1) * items_per_page
        current_list = users[start:end]

        keyboard = []
        for item in current_list:
            name = item[1] if chat_type == "group" else f"{item[2] or ''} {item[3] or ''}".strip()
            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{item[0]}")])

        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_by_{chat_type}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="ignore"))
        if end < len(users): nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"chat_by_{chat_type}_{page+1}"))
        
        if nav: keyboard.append(nav)
        keyboard.append([InlineKeyboardButton("🔍 Пошук", callback_data=f"search_chat_user_{chat_type}")])
        keyboard.append([InlineKeyboardButton("❌ Назад", callback_data="back_chat_menu")])

        await query.edit_message_text(f"{title}\nСторінка {page+1}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 3. --- ПЕРЕГЛЯД КОНКРЕТНОЇ ІСТОРІЇ (Те, що ми правили раніше) ---
    elif data.startswith("view_chat_") or data.startswith("group_chat_") or data.startswith("chat_"):
        parts = data.split("_")
        entity_id = int(parts[-1])
        messages = []
        
        if "group" in data:
            messages = db.get_chat_history(group_id=entity_id)
            title = "👥 Чат групи"
        else:
            messages = db.get_chat_history(user1_id=user_id, user2_id=entity_id)
            title = "💬 Особистий чат"

        if not messages:
            await query.edit_message_text(f"{title}\n\n❌ Повідомлень немає.", 
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_chat_menu")]]))
            return

        context.user_data['current_chat_messages'] = messages
        context.user_data['current_chat_title'] = title
        context.user_data['current_page'] = 0
        
        from handlers.common import show_chat_page
        await show_chat_page(query, context, 0)
        return

    # 4. --- ПАГІНАЦІЯ СТОРІНОК ЧАТУ ---
    elif data.startswith("chat_page_"):
        parts = data.split("_")
        page_number = int(parts[2])
        from handlers.common import show_chat_page
        await show_chat_page(query, context, page_number)
        return

    elif data in ["cancel_chat", "cancel_teacher_chat"]:
        await query.edit_message_text("Скасовано.")
        return

    # --- СТАРТ ЧАТІВ ---
    if data.startswith("chat_teacher_"):
        teacher_id = int(data.split("_")[2])
        context.user_data['chat_with'] = teacher_id
        context.user_data['chat_type'] = 'individual'
        teacher = db.get_user(teacher_id)
        await query.edit_message_text(f"💬 Чат з викладачем {teacher[2]} {teacher[3]}\n\nНапишіть ваше повідомлення:")
        return

    elif data.startswith("chat_group_"):
        group_id = int(data.split("_")[2])
        context.user_data['chat_with_group'] = group_id
        context.user_data['chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        await query.edit_message_text(
            f"👥 Чат з групою {group[1] if group else 'Невідомо'}\n\nНапишіть ваше повідомлення:")
        return

    elif data in ["cancel_chat", "cancel_teacher_chat"]:
        await query.edit_message_text("Скасовано.")
        return

    # --- ПЕРЕГЛЯД ІСТОРІЇ (ПАГІНАЦІЯ) ---
    elif data.startswith("chat_by_"):
        parts = data.split("_")
        chat_type = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0

        context.user_data['chat_filter_type'] = chat_type
        items_per_page = 10

        if chat_type == "student":
            users = db.get_users_by_role('student')
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

        total_pages = (len(users) + items_per_page - 1) // items_per_page
        start = page * items_per_page
        end = start + items_per_page
        current_list = users[start:end]

        keyboard = []
        for item in current_list:
            name = item[1] if chat_type == "group" else f"{item[2] or ''} {item[3] or ''}".strip() or "Без імені"
            keyboard.append([InlineKeyboardButton(f"{label} {name}", callback_data=f"{prefix}_{item[0]}")])

        nav_buttons = []
        if page > 0: nav_buttons.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"chat_by_{chat_type}_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="ignore"))
        if end < len(users): nav_buttons.append(
            InlineKeyboardButton("Вперед ➡️", callback_data=f"chat_by_{chat_type}_{page + 1}"))

        if nav_buttons: keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("🔍 Пошук за ім'ям", callback_data=f"search_chat_user_{chat_type}")])
        keyboard.append(
            [InlineKeyboardButton("❌ Скасувати", callback_data="back_chat_menu")])  # Перевір, куди веде back_chat_menu

        await query.edit_message_text(f"💬 {title}\nСторінка {page + 1} з {total_pages}",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("search_chat_user_"):
        chat_type = data.split("_")[3]
        context.user_data['waiting_for_search_name'] = True
        context.user_data['search_chat_type'] = chat_type
        await query.edit_message_text("🔎 **Введіть ім'я або прізвище (або частину):**", parse_mode="Markdown")
        return

    # --- ПЕРЕГЛЯД КОНКРЕТНОГО ЧАТУ (ІСТОРІЯ) ---
    elif data.startswith("view_chat_"):
        parts = data.split("_")
        messages = []
        title = ""
        
        # parts може бути: ['view', 'chat', 'student', '123'] або ['view', 'chat', 'student', 'teacher', '123']
        # Тому ID завжди беремо як останній елемент, а тип — як третій.
        entity_type = parts[2]
        entity_id = int(parts[-1])

        # 1. ЛОГІКА ДЛЯ УЧНЯ
        if user_role == 'student':
            if "teacher" in data:
                teacher = db.get_user(entity_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=entity_id)
                title = f"👨‍🏫 Чат з викладачем: {teacher[2]} {teacher[3]}"
            elif "group" in data:
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Чат групи: {group_data[1]}"

        # 2. ЛОГІКА ДЛЯ ВИКЛАДАЧА
        elif user_role == 'teacher':
            if "student" in data:
                student = db.get_user(entity_id)
                messages = db.get_chat_history(user1_id=user_id, user2_id=entity_id)
                title = f"👨‍做 Чат з учнем: {student[2]} {student[3]}"
            elif "group" in data:
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Чат групи: {group_data[1]}"

        # 3. ЛОГІКА ДЛЯ АДМІНА
        # 3. ЛОГІКА ДЛЯ АДМІНІСТРАТОРА
        elif user_role == 'admin':
            entity_id = int(parts[3])
            context.user_data['current_chat_entity_id'] = entity_id
            context.user_data['current_chat_entity_type'] = entity_type

            if entity_type == "group":
                group_data = db.get_group_by_id(entity_id)
                messages = db.get_chat_history(group_id=entity_id)
                title = f"👥 Адмін: Чат групи {group_data[1]}"
            
            elif entity_type == "student" or entity_type == "teacher":
                user_entity = db.get_user(entity_id)
                import sqlite3
                conn = sqlite3.connect(db.db_name)
                cursor = conn.cursor()
                
                # ШУКАЄМО ВСЕ: і де він отримувач, і де відправник, і групові, і особисті
                query = '''
                    SELECT m.*, u.first_name, u.last_name 
                    FROM messages m
                    LEFT JOIN users u ON m.from_user_id = u.user_id
                    WHERE m.from_user_id = ? OR m.to_user_id = ?
                    ORDER BY m.timestamp DESC
                '''
                cursor.execute(query, (entity_id, entity_id))
                messages = cursor.fetchall()
                conn.close()
                
                icon = "👨‍🎓" if entity_type == "student" else "👨‍🏫"
                name = f"{user_entity[2]} {user_entity[3]}" if user_entity else f"ID: {entity_id}"
                title = f"{icon} Вся історія: {name}"

        # ОБРОБКА РЕЗУЛЬТАТУ
        if not messages:
            back_call = f"chat_by_{entity_type}_0" if user_role == 'admin' else "back_chat_menu"
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=back_call)]]
            await query.edit_message_text(f"{title}\n\n❌ Повідомлень ще немає.",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # ПАГІНАЦІЯ ТА ВИВІД
        context.user_data['current_chat_messages'] = messages
        context.user_data['current_chat_title'] = title
        context.user_data['current_page'] = 0

        try:
            from handlers.common import show_chat_page
            await show_chat_page(query, context, 0)
        except ImportError:
            await query.edit_message_text("Помилка: функція відображення чату не знайдена.")
        return

    elif data.startswith("chat_page_"):
        parts = data.split("_")
        page_number = int(parts[2])
        files_only = len(parts) > 3 and parts[3] == "1"
        context.user_data['current_page'] = page_number
        from handlers.common import show_chat_page
        await show_chat_page(query, context, page_number, files_only=files_only)
        return

    # --- ПІДТРИМКА CONVERSATION HANDLERS ДЛЯ ЧАТІВ ---
    # У тебе в ConversationHandler є точки входу через ці кнопки.
    # Вони мають повертати стан.

    elif data.startswith("teacher_chat_student_"):
        student_id = int(data.split("_")[3])
        context.user_data['teacher_chat_with'] = student_id
        context.user_data['teacher_chat_type'] = 'individual'
        student = db.get_user(student_id)
        await query.edit_message_text(f"✅ Чат з учнем {student[2]} {student[3]} розпочато.", reply_markup=None)
        # await context.bot.send_message(query.from_user.id, "Напишіть ваше повідомлення:", reply_markup=get_chat_active_keyboard())
        return TEACHER_CHAT_ACTIVE

    elif data.startswith("teacher_chat_group_"):
        group_id = int(data.split("_")[3])
        context.user_data['teacher_chat_with_group'] = group_id
        context.user_data['teacher_chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        await query.edit_message_text(f"✅ Чат з групою {group[1] if group else 'Невідомо'} розпочато.",
                                      reply_markup=None)
        return TEACHER_CHAT_ACTIVE

    elif data.startswith("student_chat_teacher_"):
        teacher_id = int(data.split("_")[3])
        context.user_data['student_chat_with'] = teacher_id
        context.user_data['student_chat_type'] = 'individual'
        teacher = db.get_user(teacher_id)
        await query.edit_message_text(f"✅ Чат з викладачем {teacher[2]} {teacher[3]} розпочато.", reply_markup=None)
        return STUDENT_CHAT_ACTIVE

    elif data.startswith("student_chat_group_"):
        group_id = int(data.split("_")[3])
        context.user_data['student_chat_with_group'] = group_id
        context.user_data['student_chat_type'] = 'group'
        groups = db.get_all_groups()
        group = next((g for g in groups if g[0] == group_id), None)
        await query.edit_message_text(f"✅ Чат з групою {group[1] if group else 'Невідомо'} розпочато.",
                                      reply_markup=None)
        return STUDENT_CHAT_ACTIVE
