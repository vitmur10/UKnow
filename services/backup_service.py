import os
import shutil
from datetime import datetime


async def create_backup(db_name: str, backup_dir: str):
    """Створює резервну копію бази даних і повертає шлях до файлу."""

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)  # Це на всяк випадок

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}_{db_name}"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        shutil.copyfile(db_name, backup_path)
        return backup_path
    except Exception as e:
        print(f"Помилка створення резервної копії: {e}")
        return None