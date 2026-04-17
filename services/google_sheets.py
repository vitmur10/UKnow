def send_to_google(sheet_name, row_data, is_bulk=False):
    """Надсилає дані в Google. Якщо is_bulk=True, то row_data — це список списків."""
    try:
        # Якщо це один рядок, загортаємо його в список для універсальності скрипта
        payload = {
            "sheetName": sheet_name,
            "values": row_data if is_bulk else [row_data]
        }

        response = requests.post(
            GOOGLE_SCRIPT_URL,
            json=payload,
            timeout=30  # Збільшимо таймаут для великої пачки даних
        )

        if response.status_code == 200:
            print(f"✅ Google успішно оновив вкладку: {sheet_name}")
            return True
        else:
            print(f"❌ Помилка Google: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Помилка з'єднання: {e}")
        return False


async def sync_students_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Синхронізація...")
    try:
        students = db.get_users_by_role('student')
        all_groups = db.get_all_groups()
        all_rows = []

        import sqlite3
        conn = sqlite3.connect(db.db_name)
        cursor = conn.cursor()

        for s in students:
            # s[0]=id, s[1]=username, s[2]=first_name, s[3]=last_name, s[5]=phone, s[7]=birthdate
            s_id = s[0]
            teacher = "-"
            group_name = "Індивідуально"

            # Шукаємо в групах
            found = False
            for g in all_groups:
                members = db.get_group_members(g[0])
                if any(m[0] == s_id for m in members):
                    group_name = g[1]
                    t = db.get_user(g[2])
                    if t: teacher = f"{t[2]} {t[3] if t[3] else ''}"
                    found = True
                    break

            # Якщо не в групі — шукаємо індивідуала
            if not found:
                cursor.execute(
                    "SELECT u.first_name, u.last_name FROM assignments a JOIN users u ON a.teacher_id = u.user_id WHERE a.student_id = ? AND a.is_active = 1",
                    (s_id,))
                res = cursor.fetchone()
                if res: teacher = f"{res[0]} {res[1] if res[1] else ''}"

            # Формуємо рядок (7 колонок)
            all_rows.append([
                str(s_id),
                f"{s[2]} {s[3] if s[3] else ''}".strip(),
                str(s[5] if s[5] else "-"),
                teacher,
                "student",
                group_name,
                str(s[7] if len(s) > 7 and s[7] else "-")
            ])

        conn.close()

        # ВІДПРАВКА
        payload = {"sheetName": "Учні", "values": all_rows}
        import requests
        requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=30)

        await update.message.reply_text(f"✅ Готово! Оброблено {len(all_rows)} учнів.")

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


async def sync_teachers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повна масова синхронізація викладачів одним пакетом"""
    user_id = update.effective_user.id
    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Доступ лише для головного адміна.")
        return

    await update.message.reply_text("👨‍🏫 Збираю дані викладачів... Зачекайте.")

    try:
        teachers = db.get_users_by_role('teacher')
        if not teachers:
            await update.message.reply_text("📭 Викладачів не знайдено.")
            return

        all_groups = db.get_all_groups()
        all_teachers_data = []  # Сюди збираємо всі рядки

        import sqlite3
        conn = sqlite3.connect(db.db_name)
        cursor = conn.cursor()

        for t in teachers:
            t_id = t[0]
            t_name = f"{t[2]} {t[3] if t[3] else ''}".strip()

            teacher_students = set()
            teacher_groups = []

            # 1. Групи
            for g in all_groups:
                if g[2] == t_id:
                    teacher_groups.append(g[1])
                    members = db.get_group_members(g[0])
                    for m in members:
                        s_name = f"{m[2]} {m[3] if m[3] else ''}".strip()
                        teacher_students.add(s_name)

            # 2. Індивідуали
            cursor.execute('''
                SELECT u.first_name, u.last_name 
                FROM assignments a
                JOIN users u ON a.student_id = u.user_id
                WHERE a.teacher_id = ? AND a.is_active = 1
            ''', (t_id,))

            for s in cursor.fetchall():
                s_name = f"{s[0]} {s[1] if s[1] else ''}".strip()
                teacher_students.add(s_name)

            # 3. Формуємо рядок для одного викладача
            students_list_str = ", ".join(teacher_students) if teacher_students else "Немає учнів"
            groups_list_str = ", ".join(teacher_groups) if teacher_groups else "Індивідуальні заняття"

            all_teachers_data.append([
                str(t_id),  # A: ID
                t_name,  # B: Ім'я
                students_list_str,  # C: Учні
                groups_list_str  # D: Групи
            ])

        conn.close()

        # 🎯 ВІДПРАВКА ВСІЄЇ ПАЧКИ (Bulk Sync)
        import requests
        payload = {
            "sheetName": "Викладачі",
            "values": all_teachers_data  # Надсилаємо масив масивів
        }

        response = requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=30)

        if response.status_code == 200:
            await update.message.reply_text(f"✅ Успішно! Синхронізовано викладачів: {len(all_teachers_data)}")
        else:
            await update.message.reply_text(f"❌ Помилка Google: {response.status_code}")

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


async def test_gs(update, context):
    await update.message.reply_text("⏳ Пробую відправити дані в таблицю...")

    # Дані для перевірки: Час, Учень, Викладач, Група
    # Переконайся, що вкладка "Уроки" в таблиці підписана саме так!
    test_row = ["14:30", "Іван Тестовий", "Олена Викладач", "Група А"]

    send_to_google("Уроки", test_row)

    await update.message.reply_text("🚀 Готово! Перевір вкладку 'Уроки' у своїй Google Таблиці.")