import os
import logging
import re
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Завантажуємо змінні з файлу .env
load_dotenv()

# ==========================================
# 1. СЕКРЕТИ ТА НАЛАШТУВАННЯ З .env
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 0))
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")
DB_NAME = os.getenv("DB_NAME", "school_bot.db")
MINIAPP_BASE_PATH = os.getenv("MINIAPP_BASE_PATH", "/miniapp/")
MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")


def _unwrap_markdown_url(value: str) -> str:
    match = MARKDOWN_LINK_RE.match(value.strip())
    if not match:
        return value
    label_url, target_url = match.groups()
    return target_url if target_url.startswith(("http://", "https://")) else label_url


def _normalize_miniapp_url(raw_url: str, base_path: str = MINIAPP_BASE_PATH) -> str:
    value = _unwrap_markdown_url((raw_url or "").strip())
    if not value:
        return ""

    parts = urlsplit(value)
    path = parts.path

    if not path or path == "/":
        clean_base = "/" + (base_path or "").strip("/")
        path = "/" if clean_base == "/" else f"{clean_base}/"

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def build_miniapp_url(start_param: str | None = None) -> str:
    if not MINIAPP_URL:
        return ""
    if not start_param:
        return MINIAPP_URL

    parts = urlsplit(MINIAPP_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["startapp"] = start_param
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


MINIAPP_URL = _normalize_miniapp_url(os.getenv("MINIAPP_URL", ""))

# ==========================================
# 2. БАЗОВІ КОНСТАНТИ
# ==========================================
MESSAGES_PER_PAGE = 20

# ==========================================
# Часовий пояс Київ та авто-завершення чату
# ==========================================
KYIV_TZ = timezone(timedelta(hours=3))
CHAT_AUTO_END_MINUTES = 5  # хвилин бездіяльності → авто-завершення


def now_kyiv() -> datetime:
    """Поточний час за Києвом (UTC+3)."""
    return datetime.now(KYIV_TZ)


def now_kyiv_str() -> str:
    """Поточний час за Києвом у форматі ДД.ММ ГГ:ХХ."""
    return now_kyiv().strftime("%d.%m %H:%M")
IMAGE_WARNING_FILE_ID = "AgACAgIAAxkBAANnaT19FCc1xzRo7jpVDg-Z1xLD9LkAAqYLaxuyKPFJTpOEh7vOf9QBAAMCAAN5AAM2BA"
BACKUP_DIR = 'backups'

# ==========================================
# 3. СПИСКИ ТА ТРИГЕРИ
# ==========================================
LANGUAGES = [
    "🇺🇸 Англійська", "🇩🇪 Німецька", "🇨🇿 Чеська", "🇮🇹 Італійська",
    "🇪🇸 Іспанська", "🇵🇱 Польська", "🇸🇰 Словацька", "🇫🇷 Французька"
]

TRIGGER_WORDS = ["допомога", "скарга", "проблема", "конфлікт", "не влаштовує"]

ALL_MAIN_MENU_BUTTONS_LIST = [
    # Кнопки УЧНЯ
    "💬 Написати викладачеві/групі", "🗓 Мій календар",
    "🏫 Про школу", "📋 Правила школи", "❓ Популярні питання",
    "📞 Написати менеджеру", "📖 Історія переписок",

    # Кнопки ВИКЛАДАЧА
    "💬 Написати групі", "📚 Мої групи",
    "➕ Додати урок",

    # Кнопки АДМІНІСТРАТОРА
    "👨‍💼 Керування користувачами", "👥 Керування групами",
    "🗓 Керування розкладом", "🗂️ Переписки / Чати",
    "📢 Масова розсилка"
]

# ==========================================
# 4. СТАНИ ДЛЯ CONVERSATION HANDLERS (Діалоги)
# ==========================================

(
    REGISTER_NAME, REGISTER_LANG, REGISTER_BIRTHDATE, REGISTER_PHONE,
    ADD_LESSON_STUDENT, ADD_LESSON_DATE, ADD_LESSON_TIME,
    ADMIN_ASSIGN, ADMIN_MESSAGE,
    CREATE_GROUP_NAME, CREATE_GROUP_TYPE, CREATE_GROUP_TEACHER, CREATE_GROUP_STUDENTS,
    TEACHER_MESSAGE_SELECT, TEACHER_MESSAGE_TEXT, TEACHER_CHAT_ACTIVE,
    CHAT_HISTORY_SELECT, CHAT_HISTORY_DATE,
    ADMIN_SELECT_USER, ADMIN_ADD_LESSON_DATE, ADMIN_ADD_LESSON_TIME,
    LESSON,
    STUDENT_MESSAGE_SELECT, STUDENT_CHAT_ACTIVE,
    BROADCAST_SELECT_TARGET, BROADCAST_WAIT_MESSAGE, BROADCAST_SELECT_LIST
) = range(27)

# ==========================================
# 5. НАЛАШТУВАННЯ ЛОГЕРА (Вивід інформації в термінал)
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
