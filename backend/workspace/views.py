import mimetypes
import uuid
from pathlib import Path

import httpx
from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import FileResponse, Http404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from channels.layers import get_channel_layer

from database.db_manager import db
from .bot_api import delete_telegram_message, send_attachment_to_student
from .telegram_auth import TelegramAuthError, issue_ws_token, validate_telegram_init_data
from .telegram_auth import verify_ws_token
from .sqlite_payloads import dialog_payload, message_payload


@csrf_exempt
@require_POST
def miniapp_auth(request):
    init_data = request.POST.get("initData", "")
    if settings.DEBUG and not init_data and getattr(settings, "MINIAPP_DEV_TEACHER_ID", None):
        teacher_id = settings.MINIAPP_DEV_TEACHER_ID
        user = db.get_user(teacher_id)
        if user and user[4] in ("teacher", "admin") and bool(user[9]):
            return JsonResponse({"ws_token": issue_ws_token(teacher_id)})

    try:
        payload = validate_telegram_init_data(init_data)
    except (TelegramAuthError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=401)

    telegram_id = int(payload["user"]["id"])
    user = db.get_user(telegram_id)
    allowed_by_db = user and user[4] in ("teacher", "admin") and bool(user[9])
    allowed_by_env = telegram_id in settings.TEACHER_MINIAPP_IDS
    if not allowed_by_db and not allowed_by_env:
        return JsonResponse({"error": "Teacher access required"}, status=403)

    return JsonResponse({"ws_token": issue_ws_token(telegram_id)})


@csrf_exempt
@require_POST
def miniapp_bootstrap(request):
    token = request.POST.get("token", "")

    try:
        teacher_id = verify_ws_token(token)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    user = db.get_user(teacher_id)
    if not user or user[4] not in ("teacher", "admin") or not bool(user[9]):
        return JsonResponse({"error": "Teacher access required"}, status=403)

    dialogs = [dialog_payload(row) for row in db.get_miniapp_dialogs(teacher_id)]
    messages = [message_payload(row, teacher_id, user[4]) for row in db.get_miniapp_history(teacher_id)]
    teachers = [
        {"id": row[0], "name": f"{row[2]} {row[3]}".strip() or row[1] or str(row[0])}
        for row in db.get_users_by_role("teacher")
    ]
    return JsonResponse({
        "role": user[4],
        "user_id": teacher_id,
        "chats": dialogs,
        "messages": messages,
        "teachers": teachers,
    })


def _require_miniapp_user(request):
    token = request.POST.get("token", "")
    teacher_id = verify_ws_token(token)
    user = db.get_user(teacher_id)
    if not user or user[4] not in ("teacher", "admin") or not bool(user[9]):
        raise PermissionError("Teacher access required")
    return teacher_id, user


def _broadcast_miniapp_state(viewer_id):
    viewer = db.get_user(viewer_id)
    if not viewer or viewer[4] not in ("teacher", "admin") or not bool(viewer[9]):
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    payload = {
        "type": "chat.history",
        "chats": [dialog_payload(row) for row in db.get_miniapp_dialogs(viewer_id)],
        "messages": [message_payload(row, viewer_id, viewer[4]) for row in db.get_miniapp_history(viewer_id)],
    }
    async_to_sync(channel_layer.group_send)(
        f"teacher_{viewer_id}",
        {
            "type": "ws.message",
            "payload": payload,
        },
    )


@csrf_exempt
@require_POST
def miniapp_update_student(request):
    try:
        user_id, user = _require_miniapp_user(request)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if user[4] != "admin":
        return JsonResponse({"error": "Admin access required"}, status=403)

    try:
        student_id = int(request.POST.get("student_id", "0"))
    except ValueError:
        return JsonResponse({"error": "Invalid student_id"}, status=400)

    previous_teacher = db.get_student_teacher(student_id)
    affected_viewers = {user_id}
    if previous_teacher:
        affected_viewers.add(int(previous_teacher[0]))

    status = request.POST.get("student_status")
    if status in {"active", "paused", "completed"}:
        db.set_student_status(student_id, status)

    teacher_id_raw = request.POST.get("teacher_id")
    if teacher_id_raw not in (None, ""):
        try:
            new_teacher_id = int(teacher_id_raw)
        except ValueError:
            return JsonResponse({"error": "Invalid teacher_id"}, status=400)
        if not db.replace_student_teacher(student_id, new_teacher_id):
            return JsonResponse({"error": "Invalid teacher_id"}, status=400)
        affected_viewers.add(new_teacher_id)

    db.update_student_profile(
        student_id,
        level=request.POST.get("level"),
        learning_format=request.POST.get("learning_format"),
        learning_goal=request.POST.get("learning_goal"),
        admin_note=request.POST.get("admin_note"),
    )
    dialogs = [dialog_payload(row) for row in db.get_miniapp_dialogs(user_id)]
    teachers = [
        {"id": row[0], "name": f"{row[2]} {row[3]}".strip() or row[1] or str(row[0])}
        for row in db.get_users_by_role("teacher")
    ]

    for viewer_id in affected_viewers:
        _broadcast_miniapp_state(viewer_id)

    return JsonResponse({"chats": dialogs, "teachers": teachers})


@csrf_exempt
@require_POST
def miniapp_message_edits(request):
    try:
        user_id, user = _require_miniapp_user(request)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if user[4] != "admin":
        return JsonResponse({"error": "Admin access required"}, status=403)

    try:
        message_id = int(request.POST.get("message_id", "0"))
    except ValueError:
        return JsonResponse({"error": "Invalid message_id"}, status=400)

    edits = []
    for row in db.get_message_edits(message_id):
        editor = db.get_user(row[4]) if row[4] else None
        edits.append({
            "id": row[0],
            "message_id": row[1],
            "previous_text": row[2] or "",
            "new_text": row[3] or "",
            "edited_by": row[4],
            "edited_by_name": f"{editor[2]} {editor[3]}".strip() if editor else "",
            "edited_at": str(row[5] or ""),
        })
    return JsonResponse({"edits": edits})


@csrf_exempt
@require_POST
def miniapp_mark_read(request):
    try:
        user_id, user = _require_miniapp_user(request)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        student_id = int(request.POST.get("student_id", "0"))
    except ValueError:
        return JsonResponse({"error": "Invalid student_id"}, status=400)

    if user[4] != "admin" and not db.teacher_can_access_student(user_id, student_id):
        return JsonResponse({"error": "Forbidden"}, status=403)
    if user[4] != "admin":
        db.mark_messages_read(from_user_id=student_id, to_user_id=user_id)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def miniapp_delete_message(request):
    try:
        user_id, user = _require_miniapp_user(request)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        message_id = int(request.POST.get("message_id", "0"))
    except ValueError:
        return JsonResponse({"error": "Invalid message_id"}, status=400)

    row = db.get_message_by_id(message_id)
    if not row:
        return JsonResponse({"error": "Message not found"}, status=404)

    if user[4] != "admin" and int(row[1]) != int(user_id):
        return JsonResponse({"error": "Forbidden"}, status=403)

    student_id = row[2] if int(row[1]) == int(user_id) else row[1]
    if user[4] != "admin" and not db.teacher_can_access_student(user_id, student_id):
        return JsonResponse({"error": "Forbidden"}, status=403)

    db.mark_message_deleted(message_id, user_id)
    updated_row = db.get_message_by_id(message_id)

    try:
        deliveries = db.get_deliveries(message_id)
        for chat_id, tg_message_id in deliveries:
            async_to_sync(delete_telegram_message)(chat_id, tg_message_id)
    except Exception:
        pass

    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"teacher_{user_id}",
                {
                    "type": "ws.message",
                    "payload": {
                        "type": "chat.delete",
                        "message": message_payload(updated_row, user_id, user[4]),
                    },
                },
            )
    except Exception:
        pass

    return JsonResponse({"message": message_payload(updated_row, user_id, user[4])})


def _resolve_reply_to_tg_message_id(reply_to_message_id, chat_id):
    if not reply_to_message_id:
        return None
    try:
        return db.get_delivery_tg_message_id(reply_to_message_id, chat_id)
    except Exception:
        return None


@csrf_exempt
@require_POST
def miniapp_upload_attachment(request):
    try:
        user_id, user = _require_miniapp_user(request)
    except Exception:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if user[4] != "teacher":
        return JsonResponse({"error": "Teacher access required"}, status=403)

    try:
        student_id = int(request.POST.get("student_id", "0"))
    except ValueError:
        return JsonResponse({"error": "Invalid student_id"}, status=400)
    if not db.teacher_can_access_student(user_id, student_id):
        return JsonResponse({"error": "Forbidden"}, status=403)

    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "File required"}, status=400)

    original_name = Path(upload.name or "attachment").name
    mime_type = upload.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    kind = _media_kind(mime_type, original_name)
    suffix = Path(original_name).suffix or mimetypes.guess_extension(mime_type) or ".bin"

    media_dir = Path(settings.MEDIA_ROOT) / "miniapp_uploads"
    media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"miniapp-{uuid.uuid4()}{suffix}"
    media_path = media_dir / filename
    with open(media_path, "wb") as target:
        for chunk in upload.chunks():
            target.write(chunk)

    caption = (request.POST.get("caption") or "").strip()
    reply_to_raw = request.POST.get("reply_to_message_id") or None
    try:
        reply_to_message_id = int(reply_to_raw) if reply_to_raw else None
    except ValueError:
        return JsonResponse({"error": "Invalid reply_to_message_id"}, status=400)
    reply_to_tg_message_id = _resolve_reply_to_tg_message_id(reply_to_message_id, student_id)

    message_id = db.save_message(
        from_user_id=user_id,
        to_user_id=student_id,
        group_id=None,
        message_text=caption,
        message_type=kind,
        file_id=filename,
        reply_to_message_id=reply_to_message_id,
        original_filename=original_name,
        mime_type=mime_type,
    )
    try:
        sent_message_id = async_to_sync(send_attachment_to_student)(
            student_id,
            str(media_path),
            kind,
            caption,
            reply_to_tg_message_id,
        )
    except Exception:
        return JsonResponse({"error": "Не вдалося надіслати файл у Telegram"}, status=502)
    if sent_message_id:
        db.save_delivery(message_id, student_id, sent_message_id)

    row = db.get_message_by_id(message_id)
    return JsonResponse({"message": message_payload(row, user_id, user[4])})


def _media_kind(mime_type, filename):
    mime_type = mime_type or mimetypes.guess_type(filename)[0] or ""
    if mime_type.startswith("image/"):
        return "photo"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "document"


@require_GET
def message_voice(request, message_id):
    row = db.get_message_by_id(message_id)
    if not row or row[5] != "voice" or not row[8]:
        raise Http404("Voice message not found")

    file_id = row[8]
    cache_dir = Path(settings.MEDIA_ROOT) / "telegram_voice"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{message_id}.oga"
    if cached.exists():
        return FileResponse(open(cached, "rb"), content_type="audio/ogg")

    response = httpx.get(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile",
        params={"file_id": file_id},
        timeout=30,
    )
    response.raise_for_status()
    file_path = response.json()["result"]["file_path"]
    media = httpx.get(
        f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}",
        timeout=30,
    )
    media.raise_for_status()
    cached.write_bytes(media.content)
    return FileResponse(open(cached, "rb"), content_type="audio/ogg")


@require_GET
def message_media(request, message_id):
    row = db.get_message_by_id(message_id)
    if not row or not row[8]:
        raise Http404("Media not found")

    message_type = row[5] or "document"
    file_id = row[8]
    mime_type = row[19] or "application/octet-stream"

    if file_id.startswith("miniapp-"):
        local_path = Path(settings.MEDIA_ROOT) / "miniapp_uploads" / file_id
        if not local_path.exists():
            local_path = Path(settings.MEDIA_ROOT) / "miniapp_voice" / file_id
        if not local_path.exists():
            raise Http404("Media not found")
        return FileResponse(open(local_path, "rb"), content_type=mime_type)

    cache_dir = Path(settings.MEDIA_ROOT) / "telegram_media"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{message_id}-{message_type}"
    if cached.exists():
        return FileResponse(open(cached, "rb"), content_type=mime_type)

    response = httpx.get(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile",
        params={"file_id": file_id},
        timeout=30,
    )
    response.raise_for_status()
    file_path = response.json()["result"]["file_path"]
    media = httpx.get(
        f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}",
        timeout=30,
    )
    media.raise_for_status()
    cached.write_bytes(media.content)
    return FileResponse(open(cached, "rb"), content_type=mime_type)
