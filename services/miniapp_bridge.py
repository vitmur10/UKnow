import asyncio
import os
import sys
from pathlib import Path

from database.db_manager import db

_BOOTSTRAPPED = False


def _enabled() -> bool:
    return os.getenv("MINIAPP_BRIDGE_ENABLED", "0") == "1"


def _bootstrap_django():
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return True
    if not _enabled():
        return False

    backend_path = Path(__file__).resolve().parent.parent / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "miniapp_backend.settings")

    import django

    django.setup()
    _BOOTSTRAPPED = True
    return True


def _teacher_id_for_direct_message(from_user_id: int, to_user_id: int | None):
    if not to_user_id:
        return None

    sender = db.get_user(from_user_id)
    recipient = db.get_user(to_user_id)
    if sender and sender[4] in ("teacher", "admin"):
        return from_user_id
    if recipient and recipient[4] in ("teacher", "admin"):
        return to_user_id
    return None


async def mirror_message_to_miniapp(
    *,
    sqlite_message_id: int,
    from_user_id: int,
    to_user_id: int | None,
    message_text: str,
    message_type: str,
    file_id: str | None,
    telegram_message_id: int | None,
):
    if not _enabled() or not to_user_id:
        return

    try:
        if not _bootstrap_django():
            return

        from channels.layers import get_channel_layer
        from workspace.sqlite_payloads import message_payload

        teacher_id = await asyncio.to_thread(_teacher_id_for_direct_message, from_user_id, to_user_id)
        if not teacher_id:
            return

        row = await asyncio.to_thread(db.get_message_by_id, sqlite_message_id)
        if not row:
            return

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"teacher_{teacher_id}",
            {
                "type": "ws.message",
                "payload": {
                    "type": "chat.message",
                    "message": message_payload(row, teacher_id),
                },
            },
        )
    except Exception as exc:
        print(f"[miniapp] bridge message error: {exc}")


async def mirror_delete_to_miniapp(sqlite_message_id: int):
    if not _enabled():
        return

    try:
        if not _bootstrap_django():
            return

        from channels.layers import get_channel_layer
        from workspace.sqlite_payloads import message_payload

        row = await asyncio.to_thread(db.get_message_by_id, sqlite_message_id)
        if not row:
            return

        teacher_id = await asyncio.to_thread(_teacher_id_for_direct_message, row[1], row[2])
        if not teacher_id:
            return

        channel_layer = get_channel_layer()
        row_after_delete = await asyncio.to_thread(db.get_message_by_id, sqlite_message_id)
        await channel_layer.group_send(
            f"teacher_{teacher_id}",
            {
                "type": "ws.message",
                "payload": {
                    "type": "chat.delete",
                    "message_id": sqlite_message_id,
                    "message": message_payload(row_after_delete, teacher_id) if row_after_delete else None,
                },
            },
        )
    except Exception as exc:
        print(f"[miniapp] bridge delete error: {exc}")
