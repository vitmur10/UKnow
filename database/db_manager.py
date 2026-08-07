import sqlite3


class Database:
    def __init__(self, db_name="school_bot.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT DEFAULT 'student',
            phone TEXT,
            language TEXT,
            birthdate TEXT,
            hub_chat_id INTEGER,
            registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            student_id INTEGER,
            topic_id INTEGER,
            assigned_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (teacher_id) REFERENCES users (user_id),
            FOREIGN KEY (student_id) REFERENCES users (user_id)
        )''')
        # Teacher Hubs / Forum Topics migrations.
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN hub_chat_id INTEGER")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE assignments ADD COLUMN topic_id INTEGER")
        except Exception:
            pass
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_users_hub_chat_id
                          ON users (hub_chat_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_assignments_topic_id
                          ON assignments (topic_id)
                          WHERE topic_id IS NOT NULL AND is_active = 1''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER,
                    to_user_id INTEGER,
                    group_id INTEGER,
                    message_text TEXT,
                    message_type TEXT DEFAULT 'text',
                    file_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_read BOOLEAN DEFAULT 0,
                    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                    FOREIGN KEY (to_user_id) REFERENCES users (user_id),
                    FOREIGN KEY (group_id) REFERENCES groups (id)
                )''')
        # Міграція: додаємо is_read якщо таблиця вже існує без нього
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN is_read BOOLEAN DEFAULT 0")
        except Exception:
            pass
        # Міграція: додаємо file_id для збереження фото/документів
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN file_id TEXT")
        except Exception:
            pass
        # Міграція: прапорець "видалено для всіх"
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN is_deleted BOOLEAN DEFAULT 0")
        except Exception:
            pass

        # Доставлені копії повідомлень (для функції "видалити для всіх"):
        # для кожного запису messages зберігаємо telegram message_id у кожному чаті,
        # куди його було доставлено (включно з чатом відправника).
        cursor.execute('''CREATE TABLE IF NOT EXISTS delivered_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_db_id INTEGER,
            chat_id INTEGER,
            tg_message_id INTEGER,
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_db_id) REFERENCES messages (id)
        )''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_delivered_lookup
                          ON delivered_messages (chat_id, tg_message_id)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            student_id INTEGER,
            group_id INTEGER,
            lesson_date DATE,
            lesson_time TIME,
            duration INTEGER DEFAULT 60,
            status TEXT DEFAULT 'scheduled',
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users (user_id),
            FOREIGN KEY (student_id) REFERENCES users (user_id),
            FOREIGN KEY (group_id) REFERENCES groups (id)
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            teacher_id INTEGER,
            topic_id INTEGER,
            group_type TEXT DEFAULT 'pair',
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (teacher_id) REFERENCES users (user_id)
        )''')
        try:
            cursor.execute("ALTER TABLE groups ADD COLUMN topic_id INTEGER")
        except Exception:
            pass
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_groups_topic_id
                          ON groups (topic_id)
                          WHERE topic_id IS NOT NULL AND is_active = 1''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER,
            student_id INTEGER,
            joined_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (group_id) REFERENCES groups (id),
            FOREIGN KEY (student_id) REFERENCES users (user_id)
        )''')

        conn.commit()
        conn.close()

    def cancel_lesson(self, lesson_id):
        """Скасувати урок"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE lessons SET status = 'cancelled' WHERE id = ?", (lesson_id,))
        conn.commit()
        conn.close()
        return True

    def get_admin_list(self):
        """Получить список всех администраторов"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE role = 'admin' AND is_active = 1")
        result = cursor.fetchall()
        conn.close()
        return result

    def remove_admin_rights(self, user_id):
        """Убрать права администратора"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'student' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def get_lesson_by_id(self, lesson_id):
        """Отримати урок за ID"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT l.*, 
                                 t.first_name as teacher_first, t.last_name as teacher_last,
                                 s.first_name as student_first, s.last_name as student_last,
                                 g.name as group_name
                          FROM lessons l
                          LEFT JOIN users t ON l.teacher_id = t.user_id
                          LEFT JOIN users s ON l.student_id = s.user_id  
                          LEFT JOIN groups g ON l.group_id = g.id
                          WHERE l.id = ?''', (lesson_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def get_active_lessons_for_student(self, student_id):
        """Отримати активні уроки студента"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                         LEFT JOIN users u ON l.teacher_id = u.user_id
                         LEFT JOIN groups g ON l.group_id = g.id
                         WHERE (l.student_id = ? OR l.group_id IN 
                               (SELECT group_id FROM group_members WHERE student_id = ? AND is_active = 1))
                         AND l.lesson_date >= date('now') AND l.status = 'scheduled'
                         ORDER BY l.lesson_date, l.lesson_time''', (student_id, student_id))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_active_lessons_for_teacher(self, teacher_id):
        """Отримати активні уроки викладача"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                         LEFT JOIN users u ON l.student_id = u.user_id
                         LEFT JOIN groups g ON l.group_id = g.id
                         WHERE l.teacher_id = ? AND l.lesson_date >= date('now') AND l.status = 'scheduled'
                         ORDER BY l.lesson_date, l.lesson_time''', (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_active_lessons_for_group(self, group_id):
        """Отримати активні уроки групи"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT l.*, u.first_name, u.last_name FROM lessons l
                         JOIN users u ON l.teacher_id = u.user_id
                         WHERE l.group_id = ? AND l.lesson_date >= date('now') AND l.status = 'scheduled'
                         ORDER BY l.lesson_date, l.lesson_time''', (group_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def add_user(self, user_id, username, first_name, last_name, role='student'):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute('''UPDATE users
                              SET username = ?, first_name = ?, last_name = ?, role = ?, is_active = 1
                              WHERE user_id = ?''',
                           (username, first_name, last_name, role, user_id))
        else:
            cursor.execute('''INSERT INTO users
                             (user_id, username, first_name, last_name, role)
                             VALUES (?, ?, ?, ?, ?)''',
                           (user_id, username, first_name, last_name, role))
        conn.commit()
        conn.close()

    def update_user_info(self, user_id, phone=None, language=None, birthdate=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        updates = []
        params = []

        if phone:
            updates.append("phone = ?")
            params.append(phone)
        if language:
            updates.append("language = ?")
            params.append(language)
        if birthdate:
            updates.append("birthdate = ?")
            params.append(birthdate)

        if updates:
            params.append(user_id)
            query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
            cursor.execute(query, params)

        conn.commit()
        conn.close()

    def get_user(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def get_users_by_role(self, role):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE role = ? AND is_active = 1", (role,))
        result = cursor.fetchall()
        conn.close()
        return result

    def assign_teacher_to_student(self, teacher_id, student_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # Deactivate old assignments
        cursor.execute("UPDATE assignments SET is_active = 0 WHERE student_id = ?", (student_id,))
        # Create new assignment
        cursor.execute('''INSERT INTO assignments (teacher_id, student_id) 
                         VALUES (?, ?)''', (teacher_id, student_id))
        conn.commit()
        conn.close()

    def get_hub_chat_id(self, teacher_id):
        """Повертає Telegram chat_id супергрупи-хабу викладача або None."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT hub_chat_id FROM users
                          WHERE user_id = ? AND role = 'teacher' AND is_active = 1''',
                       (teacher_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None

    def set_hub_chat_id(self, teacher_id, chat_id):
        """Зберігає Telegram chat_id супергрупи-хабу викладача."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET hub_chat_id = ? WHERE user_id = ?",
                       (chat_id, teacher_id))
        conn.commit()
        conn.close()

    def get_user_topic_id(self, student_id):
        """Повертає forum topic_id активної індивідуальної прив'язки учня."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT topic_id FROM assignments
                          WHERE student_id = ? AND is_active = 1
                          ORDER BY assigned_date DESC, id DESC
                          LIMIT 1''', (student_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None

    def set_user_topic_id(self, student_id, topic_id):
        """Зберігає forum topic_id для активної індивідуальної прив'язки учня."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''UPDATE assignments SET topic_id = ?
                          WHERE student_id = ? AND is_active = 1''',
                       (topic_id, student_id))
        conn.commit()
        conn.close()

    def get_assignment_topic_id(self, teacher_id, student_id):
        """Повертає topic_id для конкретної активної пари викладач-учень."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT topic_id FROM assignments
                          WHERE teacher_id = ? AND student_id = ? AND is_active = 1
                          ORDER BY assigned_date DESC, id DESC
                          LIMIT 1''', (teacher_id, student_id))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None

    def set_assignment_topic_id(self, teacher_id, student_id, topic_id):
        """Зберігає topic_id для конкретної активної пари викладач-учень."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''UPDATE assignments SET topic_id = ?
                          WHERE teacher_id = ? AND student_id = ? AND is_active = 1''',
                       (topic_id, teacher_id, student_id))
        conn.commit()
        conn.close()

    def get_teacher_students_with_chat_history(self, teacher_id):
        """
        Активні учні викладача, з якими вже є direct messages.
        Повертає: user_id, username, first_name, last_name, role, topic_id, messages_count.
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT u.user_id, u.username, u.first_name, u.last_name, u.role,
                                 a.topic_id, COUNT(m.id) AS messages_count
                          FROM assignments a
                          JOIN users u ON u.user_id = a.student_id
                          JOIN messages m ON (
                              (m.from_user_id = a.student_id AND m.to_user_id = a.teacher_id)
                              OR (m.from_user_id = a.teacher_id AND m.to_user_id = a.student_id)
                          )
                          WHERE a.teacher_id = ?
                            AND a.is_active = 1
                            AND u.is_active = 1
                            AND m.group_id IS NULL
                          GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.role, a.topic_id
                          ORDER BY u.first_name, u.last_name''', (teacher_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_student_by_topic_id(self, topic_id, hub_chat_id=None):
        """
        Повертає рядок users для учня за topic_id.
        Якщо передано hub_chat_id, додатково перевіряє, що topic належить
        викладачу саме цього Teacher Hub.
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        query = '''SELECT s.* FROM assignments a
                   JOIN users s ON s.user_id = a.student_id
                   JOIN users t ON t.user_id = a.teacher_id
                   WHERE a.topic_id = ? AND a.is_active = 1 AND s.is_active = 1'''
        params = [topic_id]
        if hub_chat_id is not None:
            query += " AND t.hub_chat_id = ?"
            params.append(hub_chat_id)
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        return row

    def get_teacher_by_hub_chat_id(self, hub_chat_id):
        """Повертає викладача за chat_id його супергрупи-хабу."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM users
                          WHERE hub_chat_id = ? AND role = 'teacher' AND is_active = 1''',
                       (hub_chat_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def get_group_topic_id(self, group_id):
        """Повертає forum topic_id навчальної групи або None."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT topic_id FROM groups
                          WHERE id = ? AND is_active = 1''', (group_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None

    def set_group_topic_id(self, group_id, topic_id):
        """Зберігає forum topic_id для навчальної групи."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE groups SET topic_id = ? WHERE id = ?",
                       (topic_id, group_id))
        conn.commit()
        conn.close()

    def get_group_by_topic_id(self, topic_id, hub_chat_id=None):
        """Повертає групу за topic_id, опційно перевіряючи Teacher Hub викладача."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        query = '''SELECT g.* FROM groups g
                   JOIN users t ON t.user_id = g.teacher_id
                   WHERE g.topic_id = ? AND g.is_active = 1'''
        params = [topic_id]
        if hub_chat_id is not None:
            query += " AND t.hub_chat_id = ?"
            params.append(hub_chat_id)
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        return row

    # def get_teacher_students(self, teacher_id):
    # conn = sqlite3.connect(self.db_name)
    # cursor = conn.cursor()
    # cursor.execute('''SELECT u.* FROM users u
    # JOIN assignments a ON u.user_id = a.student_id
    # WHERE a.teacher_id = ? AND a.is_active = 1''', (teacher_id,))
    # result = cursor.fetchall()
    # conn.close()
    # return result

    def get_student_teacher(self, student_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT u.* FROM users u 
                         JOIN assignments a ON u.user_id = a.teacher_id 
                         WHERE a.student_id = ? AND a.is_active = 1''', (student_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def create_group(self, name, teacher_id, group_type='pair'):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO groups (name, teacher_id, group_type) 
                         VALUES (?, ?, ?)''', (name, teacher_id, group_type))
        group_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return group_id

    def add_student_to_group(self, group_id, student_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO group_members (group_id, student_id) 
                         VALUES (?, ?)''', (group_id, student_id))
        conn.commit()
        conn.close()

    def get_teacher_groups(self, teacher_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE teacher_id = ? AND is_active = 1", (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_group_members(self, group_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT u.* FROM users u 
                         JOIN group_members gm ON u.user_id = gm.student_id 
                         WHERE gm.group_id = ? AND gm.is_active = 1''', (group_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_student_groups(self, student_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT g.* FROM groups g 
                         JOIN group_members gm ON g.id = gm.group_id 
                         WHERE gm.student_id = ? AND gm.is_active = 1 AND g.is_active = 1''', (student_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_all_groups(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE is_active = 1")
        result = cursor.fetchall()
        conn.close()
        return result

    def get_group(self, group_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def remove_student_from_group(self, group_id, student_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE group_members SET is_active = 0 WHERE group_id = ? AND student_id = ?",
                       (group_id, student_id))
        conn.commit()
        conn.close()

    def change_group_teacher(self, group_id, new_teacher_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE groups SET teacher_id = ? WHERE id = ?", (new_teacher_id, group_id))
        conn.commit()
        conn.close()

    def add_lesson(self, teacher_id, student_id=None, group_id=None, lesson_date=None, lesson_time=None, duration=60):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        # Convert date and time objects to strings for SQLite
        lesson_date_str = lesson_date.strftime('%Y-%m-%d') if lesson_date else None
        lesson_time_str = lesson_time.strftime('%H:%M:%S') if lesson_time else None

        cursor.execute('''INSERT INTO lessons 
                         (teacher_id, student_id, group_id, lesson_date, lesson_time, duration) 
                         VALUES (?, ?, ?, ?, ?, ?)''',
                       (teacher_id, student_id, group_id, lesson_date_str, lesson_time_str, duration))
        lesson_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return lesson_id

    def get_student_lessons(self, student_id, date=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        if date:
            # Преобразуем дату в строку если она передана как объект date
            if hasattr(date, 'strftime'):
                date_str = date.strftime('%Y-%m-%d')
            else:
                date_str = str(date)

            cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                            LEFT JOIN users u ON l.teacher_id = u.user_id
                            LEFT JOIN groups g ON l.group_id = g.id
                            WHERE (l.student_id = ? OR l.group_id IN 
                                (SELECT group_id FROM group_members WHERE student_id = ? AND is_active = 1))
                            AND l.lesson_date = ? AND l.status != 'cancelled'
                            ORDER BY l.lesson_time''', (student_id, student_id, date_str))
        else:
            cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                            LEFT JOIN users u ON l.teacher_id = u.user_id
                            LEFT JOIN groups g ON l.group_id = g.id
                            WHERE (l.student_id = ? OR l.group_id IN 
                                (SELECT group_id FROM group_members WHERE student_id = ? AND is_active = 1))
                            AND l.lesson_date >= date('now') AND l.status != 'cancelled'
                            ORDER BY l.lesson_date, l.lesson_time''', (student_id, student_id))

        result = cursor.fetchall()
        conn.close()
        return result

    def get_teacher_lessons(self, teacher_id, date=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        if date:
            date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
            cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                            LEFT JOIN users u ON l.student_id = u.user_id
                            LEFT JOIN groups g ON l.group_id = g.id
                            WHERE l.teacher_id = ? AND l.lesson_date = ? AND l.status != 'cancelled'
                            ORDER BY l.lesson_time''', (teacher_id, date_str))
        else:
            cursor.execute('''SELECT l.*, u.first_name, u.last_name, g.name as group_name FROM lessons l
                            LEFT JOIN users u ON l.student_id = u.user_id
                            LEFT JOIN groups g ON l.group_id = g.id
                            WHERE l.teacher_id = ? AND l.lesson_date >= date('now') AND l.status != 'cancelled'
                            ORDER BY l.lesson_date, l.lesson_time''', (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def save_message(self, from_user_id, to_user_id=None, group_id=None, message_text="", message_type='text',
                     file_id=None):
        """Зберігає повідомлення і повертає його id у таблиці messages."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO messages
                         (from_user_id, to_user_id, group_id, message_text, message_type, file_id)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                       (from_user_id, to_user_id, group_id, message_text, message_type, file_id))
        message_db_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return message_db_id

    # ==================================================================
    # "ВИДАЛИТИ ДЛЯ ВСІХ": облік доставлених копій
    # ==================================================================

    def save_delivery(self, message_db_id, chat_id, tg_message_id):
        """Фіксує доставлену копію повідомлення у конкретному чаті."""
        if not message_db_id or not tg_message_id:
            return
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO delivered_messages (message_db_id, chat_id, tg_message_id)
                          VALUES (?, ?, ?)''', (message_db_id, chat_id, tg_message_id))
        conn.commit()
        conn.close()

    def find_message_by_delivery(self, chat_id, tg_message_id):
        """
        За (chat_id, tg_message_id) знаходить запис messages.
        Повертає (message_db_id, from_user_id) або None.
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT d.message_db_id, m.from_user_id
                          FROM delivered_messages d
                          JOIN messages m ON m.id = d.message_db_id
                          WHERE d.chat_id = ? AND d.tg_message_id = ?''',
                       (chat_id, tg_message_id))
        result = cursor.fetchone()
        conn.close()
        return result

    def get_deliveries(self, message_db_id):
        """Всі доставлені копії повідомлення: список (chat_id, tg_message_id)."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT chat_id, tg_message_id FROM delivered_messages
                          WHERE message_db_id = ?''', (message_db_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def mark_message_deleted(self, message_db_id):
        """Позначає повідомлення видаленим (текст лишається в БД для адміна)."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET is_deleted = 1 WHERE id = ?", (message_db_id,))
        conn.commit()
        conn.close()

    def get_chat_history(self, user1_id=None, user2_id=None, group_id=None,
                         date_from=None, date_to=None, include_deleted=False,
                         admin_all_chats=False):
        """
        admin_all_chats=True — адмін бачить ВСІ повідомлення де user є відправником
        АБО отримувачем (OR замість AND між user1/user2).
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        result = []

        # ВАЖЛИВО: явний перелік колонок замість m.* — гарантує стабільні індекси
        # [0]id [1]from [2]to [3]group [4]text [5]type [6]timestamp [7]is_read
        # [8]file_id [9]first_name [10]last_name [11]is_deleted
        select_cols = '''SELECT m.id, m.from_user_id, m.to_user_id, m.group_id,
                                m.message_text, m.message_type, m.timestamp,
                                m.is_read, m.file_id,
                                u.first_name, u.last_name,
                                COALESCE(m.is_deleted, 0)
                         FROM messages m
                         JOIN users u ON m.from_user_id = u.user_id'''

        if group_id:
            if include_deleted:
                query = select_cols + ' WHERE m.group_id = ?'
            else:
                query = select_cols + ' WHERE COALESCE(m.is_deleted, 0) = 0 AND m.group_id = ?'
            params = [group_id]
        elif admin_all_chats:
            # Адмін: бачить ВСІ повідомлення де user є відправником АБО отримувачем
            query = select_cols + ''' WHERE (m.from_user_id = ? OR m.to_user_id = ?)'''
            params = [user1_id, user1_id]
        else:
            if include_deleted:
                query = select_cols + ''' WHERE ((m.from_user_id = ? AND m.to_user_id = ?)
                                 OR (m.from_user_id = ? AND m.to_user_id = ?))'''
            else:
                query = select_cols + ''' WHERE COALESCE(m.is_deleted, 0) = 0
                                 AND ((m.from_user_id = ? AND m.to_user_id = ?)
                                 OR (m.from_user_id = ? AND m.to_user_id = ?))'''
            params = [user1_id, user2_id, user2_id, user1_id]

        if date_from:
            query += " AND date(m.timestamp) >= ?"
            params.append(date_from)
        if date_to:
            query += " AND date(m.timestamp) <= ?"
            params.append(date_to)

        query += " ORDER BY m.timestamp DESC"

        try:
            cursor.execute(query, params)
            result = cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Помилка при отриманні історії чату: {e}")
        finally:
            conn.close()

        return result

    # def get_teacher_students(self, teacher_id):
    # conn = sqlite3.connect(self.db_name)
    # cursor = conn.cursor()
    # cursor.execute('''SELECT u.user_id, u.username, u.first_name, u.last_name, u.role FROM users u
    # JOIN assignments a ON u.user_id = a.student_id
    # WHERE a.teacher_id = ? AND a.is_active = 1''', (teacher_id,))
    # result = cursor.fetchall()
    # conn.close()
    # return result

    def get_teacher_students(self, teacher_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''SELECT u.user_id, u.username, u.first_name, u.last_name, u.role, u.phone, u.language FROM users u 
                            JOIN assignments a ON u.user_id = a.student_id 
                            WHERE a.teacher_id = ? AND a.is_active = 1''', (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_teacher_groups(self, teacher_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE teacher_id = ? AND is_active = 1", (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_unread_count_per_student(self, teacher_id):
        """Повертає список учнів з кількістю непрочитаних повідомлень для викладача."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.from_user_id, u.first_name, u.last_name, COUNT(*) as unread,
                   MAX(m.timestamp) as last_time, MAX(m.message_text) as last_msg
            FROM messages m
            JOIN users u ON m.from_user_id = u.user_id
            WHERE m.to_user_id = ? AND m.is_read = 0 AND m.group_id IS NULL
            GROUP BY m.from_user_id
            ORDER BY last_time DESC
        ''', (teacher_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def mark_messages_read(self, from_user_id, to_user_id):
        """Позначає всі повідомлення від from_user_id до to_user_id як прочитані."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE messages SET is_read = 1
            WHERE from_user_id = ? AND to_user_id = ? AND is_read = 0
        ''', (from_user_id, to_user_id))
        conn.commit()
        conn.close()

    def get_total_unread_count(self, teacher_id):
        """Повертає загальну кількість непрочитаних повідомлень для викладача."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM messages
            WHERE to_user_id = ? AND is_read = 0 AND group_id IS NULL
        ''', (teacher_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def get_group_by_id(self, group_id):
        """Отримує групу за її ID."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE id = ? AND is_active = 1", (group_id,))
        result = cursor.fetchone()
        conn.close()
        return result


db = Database()
