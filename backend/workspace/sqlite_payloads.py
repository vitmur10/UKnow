from django.conf import settings


def initials(first_name: str, last_name: str) -> str:
    value = f"{(first_name or '')[:1]}{(last_name or '')[:1]}".strip()
    return value.upper() or "?"


def message_payload(row, teacher_id: int, viewer_role: str | None = None):
    message_id = row[0]
    from_user_id = row[1]
    to_user_id = row[2]
    text = row[4] or ""
    kind = row[5] or "text"
    file_id = row[8] or ""
    first_name = row[9] or ""
    last_name = row[10] or ""
    from_role = row[26] if len(row) > 26 else ""
    to_role = row[27] if len(row) > 27 else ""
    if from_role == "student" and to_role != "student":
        student_id = from_user_id
        sender_kind = "student"
    elif to_role == "student" and from_role != "student":
        student_id = to_user_id
        sender_kind = "teacher"
    else:
        student_id = to_user_id if int(from_user_id) == int(teacher_id) else from_user_id
        sender_kind = "teacher" if int(from_user_id) == int(teacher_id) else "student"
    is_deleted = bool(row[11])
    is_admin_view = viewer_role == "admin"

    display_text = text
    if is_deleted and not is_admin_view:
        display_text = "Повідомлення видалено"

    filename = row[18] if len(row) > 18 else ""
    mime_type = row[19] if len(row) > 19 else ""
    reply_text = row[20] if len(row) > 20 else ""
    reply_kind = row[21] if len(row) > 21 else ""
    deleted_by_name = " ".join(part for part in [
        row[22] if len(row) > 22 else "",
        row[23] if len(row) > 23 else "",
    ] if part).strip()
    edited_by_name = " ".join(part for part in [
        row[24] if len(row) > 24 else "",
        row[25] if len(row) > 25 else "",
    ] if part).strip()

    media_url = ""
    if kind == "voice":
        media_url = (
            f"{settings.MEDIA_URL}miniapp_voice/{file_id}"
            if file_id.startswith("miniapp-")
            else f"/api/messages/{message_id}/voice/"
        )
    elif kind != "text" and file_id:
        media_url = (
            f"{settings.MEDIA_URL}miniapp_uploads/{file_id}"
            if file_id.startswith("miniapp-")
            else f"/api/messages/{message_id}/media/"
        )

    return {
        "id": message_id,
        "chat_id": student_id,
        "sender_id": from_user_id,
        "sender_kind": sender_kind,
        "sender_name": f"{first_name} {last_name}".strip(),
        "kind": kind,
        "text": display_text,
        "original_text": text if is_admin_view else "",
        "file_id": file_id,
        "media_url": media_url,
        "voice_url": media_url if kind == "voice" else "",
        "filename": filename or "",
        "mime_type": mime_type or "",
        "is_deleted": is_deleted,
        "deleted_by": row[12] if len(row) > 12 else None,
        "deleted_by_name": deleted_by_name,
        "deleted_at": str(row[13] or "") if len(row) > 13 else "",
        "edited_at": str(row[14] or "") if len(row) > 14 else "",
        "edited_by": row[15] if len(row) > 15 else None,
        "edited_by_name": edited_by_name,
        "reply_to_message_id": row[16] if len(row) > 16 else None,
        "reply_preview": {
            "text": reply_text or ("Вкладення" if reply_kind and reply_kind != "text" else ""),
            "kind": reply_kind or "",
        } if (len(row) > 16 and row[16]) else None,
        "possible_contact": bool(row[17]) if len(row) > 17 else False,
        "created_at": str(row[6]),
    }


def dialog_payload(row):
    (
        student_id, first_name, last_name, username, _, last_text, last_type,
        timestamp, unread_count, last_from_user_id, language, level, student_status,
        learning_format, learning_goal, admin_note, teacher_first, teacher_last,
        teacher_id, last_is_deleted, possible_contact, next_lesson,
    ) = row
    preview = "Повідомлення видалено" if last_is_deleted else (last_text or (media_label(last_type) if last_type != "text" else ""))
    full_name = f"{first_name or ''} {last_name or ''}".strip() or username or str(student_id)
    last_sender = "student"
    if last_from_user_id and int(last_from_user_id) != int(student_id):
        last_sender = "teacher"
    teacher_name = f"{teacher_first or ''} {teacher_last or ''}".strip()

    return {
        "id": student_id,
        "student_id": student_id,
        "title": full_name,
        "subtitle": preview,
        "last_sender": last_sender,
        "waiting_reply": last_sender == "student" and bool(timestamp),
        "initials": initials(first_name, last_name),
        "username": username or "",
        "last_message_at": str(timestamp or ""),
        "unread_count": unread_count or 0,
        "language": language or "",
        "level": level or "",
        "student_status": student_status or "active",
        "is_archived": (student_status or "active") == "completed",
        "learning_format": learning_format or "",
        "learning_goal": learning_goal or "",
        "admin_note": admin_note or "",
        "next_lesson": next_lesson or "",
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "possible_contact": bool(possible_contact),
    }


def media_label(kind):
    labels = {
        "photo": "Фото",
        "video": "Відео",
        "document": "Документ",
        "audio": "Аудіо",
        "voice": "Голосове повідомлення",
        "video_note": "Відеоповідомлення",
        "animation": "GIF",
        "sticker": "Стікер",
    }
    return labels.get(kind or "", "Вкладення")
