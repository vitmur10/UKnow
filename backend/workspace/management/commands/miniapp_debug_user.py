import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from database.db_manager import db


class Command(BaseCommand):
    help = "Show miniapp diagnostics for a teacher/admin Telegram ID."

    def add_arguments(self, parser):
        parser.add_argument("telegram_id", type=int)

    def handle(self, *args, **options):
        telegram_id = options["telegram_id"]
        user = db.get_user(telegram_id)
        if not user:
            raise CommandError(f"User {telegram_id} not found")

        role = user[4]
        is_active = bool(user[9])
        conn = sqlite3.connect(db.get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM assignments WHERE teacher_id = ? AND is_active = 1", (telegram_id,))
        active_assignments = cursor.fetchone()[0]
        cursor.execute('''SELECT COUNT(DISTINCT gm.student_id)
                          FROM groups g
                          JOIN group_members gm ON gm.group_id = g.id
                          WHERE g.teacher_id = ?
                            AND g.is_active = 1
                            AND gm.is_active = 1''', (telegram_id,))
        group_students = cursor.fetchone()[0]
        conn.close()
        student_ids = db.get_miniapp_student_ids_for_teacher(telegram_id) if role != "admin" else []
        dialogs = db.get_miniapp_dialogs(telegram_id) if role in ("teacher", "admin") and is_active else []
        lessons = db.get_miniapp_lessons(telegram_id) if role in ("teacher", "admin") and is_active else []
        history = db.get_miniapp_history(telegram_id) if role in ("teacher", "admin") and is_active else []

        self.stdout.write(f"telegram_id: {telegram_id}")
        self.stdout.write(f"role: {role}")
        self.stdout.write(f"is_active: {1 if is_active else 0}")
        self.stdout.write(f"db_path: {db.get_db_path()}")
        self.stdout.write(f"django_db_name: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"teacher_scope_students: {len(student_ids) if role != 'admin' else 'ALL'}")
        self.stdout.write(f"active_assignments: {active_assignments if role != 'admin' else 'n/a'}")
        self.stdout.write(f"group_students: {group_students if role != 'admin' else 'n/a'}")
        self.stdout.write(f"miniapp_students: {len(dialogs)}")
        self.stdout.write(f"future_lessons: {len(lessons)}")
        self.stdout.write(f"messages: {len(history)}")
        if dialogs:
            self.stdout.write("sample_students:")
            for row in dialogs[:10]:
                self.stdout.write(f"  - {row[0]} | {(row[1] or '')} {(row[2] or '')}".strip())
