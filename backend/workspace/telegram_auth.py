import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings
from django.core import signing

INIT_DATA_MAX_AGE_SECONDS = 60 * 60
WS_TOKEN_MAX_AGE_SECONDS = 60 * 10


class TelegramAuthError(Exception):
    pass


def validate_telegram_init_data(init_data: str) -> dict:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Missing Telegram hash")

    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > INIT_DATA_MAX_AGE_SECONDS:
        raise TelegramAuthError("Telegram initData expired")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramAuthError("Invalid Telegram signature")
    if "user" not in parsed:
        raise TelegramAuthError("Missing Telegram user")

    parsed["user"] = json.loads(parsed["user"])
    return parsed


def issue_ws_token(teacher_telegram_id: int) -> str:
    return signing.dumps({"teacher_id": teacher_telegram_id}, salt="miniapp-ws", compress=True)


def verify_ws_token(token: str) -> int:
    data = signing.loads(token, salt="miniapp-ws", max_age=WS_TOKEN_MAX_AGE_SECONDS)
    return int(data["teacher_id"])

