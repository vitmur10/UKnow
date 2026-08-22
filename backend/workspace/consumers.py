import base64
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from database.db_manager import db

from .bot_api import (
    delete_telegram_message,
    edit_telegram_text,
    send_attachment_to_student,
    send_text_to_student,
    send_voice_to_student,
)
from .sqlite_payloads import dialog_payload, message_payload
from .telegram_auth import verify_ws_token


class TeacherChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        token = query.get("token", [None])[0]

        try:
            self.teacher_tg_id = verify_ws_token(token)
            teacher = await sync_to_async(db.get_user)(self.teacher_tg_id)
            if not teacher or teacher[4] not in ("teacher", "admin"):
                raise PermissionError
            self.viewer_role = teacher[4]
        except Exception:
            await self.close(code=4401)
            return

        self.group_name = f"teacher_{self.teacher_tg_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "chat.history",
            "chats": await self.get_dialogs(),
            "messages": await self.get_history(),
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("type")
        if event_type == "chat.message":
            await self.handle_text(content)
        elif event_type == "chat.voice":
            await self.handle_voice(content)
        elif event_type == "chat.attachment":
            await self.handle_attachment(content)
        elif event_type == "chat.delete":
            await self.handle_delete(content)
        elif event_type == "chat.edit":
            await self.handle_edit(content)
        elif event_type == "chat.read":
            await self.handle_read(content)
        else:
            await self.send_json({"type": "error", "message": "Unknown event type"})

    async def handle_text(self, content):
        student_id = int(content["chat_id"])
        text = (content.get("text") or "").strip()
        if not text or not await self.can_access(student_id):
            return

        message_id = await sync_to_async(db.save_message)(
            from_user_id=self.teacher_tg_id,
            to_user_id=student_id,
            group_id=None,
            message_text=text,
            message_type="text",
            file_id=None,
            reply_to_message_id=content.get("reply_to_message_id"),
        )
        sent_message_id = await send_text_to_student(student_id, text)
        if sent_message_id:
            await sync_to_async(db.save_delivery)(message_id, student_id, sent_message_id)

        row = await sync_to_async(db.get_message_by_id)(message_id)
        await self.broadcast({"type": "chat.message", "message": message_payload(row, self.teacher_tg_id, self.viewer_role)})

    async def handle_voice(self, content):
        student_id = int(content["chat_id"])
        if not await self.can_access(student_id):
            return

        audio_value = content.get("audio_base64", "")
        if "," in audio_value:
            audio_value = audio_value.split(",", 1)[1]
        audio_bytes = base64.b64decode(audio_value)

        media_dir = Path(settings.MEDIA_ROOT) / "miniapp_voice"
        media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"miniapp-{uuid.uuid4()}.webm"
        voice_path = media_dir / filename
        voice_path.write_bytes(audio_bytes)

        message_id = await sync_to_async(db.save_message)(
            from_user_id=self.teacher_tg_id,
            to_user_id=student_id,
            group_id=None,
            message_text="",
            message_type="voice",
            file_id=filename,
            reply_to_message_id=content.get("reply_to_message_id"),
            original_filename="voice.webm",
            mime_type="audio/webm",
        )
        sent_message_id = await send_voice_to_student(student_id, str(voice_path))
        if sent_message_id:
            await sync_to_async(db.save_delivery)(message_id, student_id, sent_message_id)

        row = await sync_to_async(db.get_message_by_id)(message_id)
        await self.broadcast({"type": "chat.message", "message": message_payload(row, self.teacher_tg_id, self.viewer_role)})

    async def handle_attachment(self, content):
        student_id = int(content["chat_id"])
        if not await self.can_access(student_id):
            return

        data_url = content.get("file_base64", "")
        if "," in data_url:
            header, raw_value = data_url.split(",", 1)
        else:
            header, raw_value = "", data_url
        file_bytes = base64.b64decode(raw_value)
        original_name = (content.get("filename") or "attachment").replace("\\", "_").replace("/", "_")
        mime_type = content.get("mime_type") or ""
        if not mime_type and header.startswith("data:"):
            mime_type = header[5:].split(";", 1)[0]

        kind = self.media_kind(mime_type, original_name)
        suffix = Path(original_name).suffix or mimetypes.guess_extension(mime_type) or ".bin"
        media_dir = Path(settings.MEDIA_ROOT) / "miniapp_uploads"
        media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"miniapp-{uuid.uuid4()}{suffix}"
        media_path = media_dir / filename
        media_path.write_bytes(file_bytes)

        caption = (content.get("caption") or "").strip()
        reply_to_message_id = content.get("reply_to_message_id")
        reply_to_tg_message_id = await sync_to_async(db.get_delivery_tg_message_id)(reply_to_message_id, student_id) if reply_to_message_id else None
        message_id = await sync_to_async(db.save_message)(
            from_user_id=self.teacher_tg_id,
            to_user_id=student_id,
            group_id=None,
            message_text=caption,
            message_type=kind,
            file_id=filename,
            reply_to_message_id=content.get("reply_to_message_id"),
            original_filename=original_name,
            mime_type=mime_type,
        )
        sent_message_id = await send_attachment_to_student(
            student_id,
            str(media_path),
            kind,
            caption,
            reply_to_tg_message_id,
        )
        if sent_message_id:
            await sync_to_async(db.save_delivery)(message_id, student_id, sent_message_id)

        row = await sync_to_async(db.get_message_by_id)(message_id)
        await self.broadcast({"type": "chat.message", "message": message_payload(row, self.teacher_tg_id, self.viewer_role)})

    async def handle_delete(self, content):
        message_id = int(content["message_id"])
        row = await sync_to_async(db.get_message_by_id)(message_id)
        if not row:
            return
        student_id = row[2] if int(row[1]) == int(self.teacher_tg_id) else row[1]
        if not await self.can_access(student_id):
            return

        await sync_to_async(db.mark_message_deleted)(message_id, self.teacher_tg_id)
        updated_row = await sync_to_async(db.get_message_by_id)(message_id)
        await self.broadcast({"type": "chat.delete", "message": message_payload(updated_row, self.teacher_tg_id, self.viewer_role)})

        deliveries = await sync_to_async(db.get_deliveries)(message_id)
        for chat_id, tg_message_id in deliveries:
            try:
                await delete_telegram_message(chat_id, tg_message_id)
            except Exception:
                pass

    async def handle_edit(self, content):
        message_id = int(content["message_id"])
        text = (content.get("text") or "").strip()
        if not text:
            return
        row = await sync_to_async(db.get_message_by_id)(message_id)
        if not row or int(row[1]) != int(self.teacher_tg_id) or row[5] != "text" or row[11]:
            return
        student_id = row[2]
        if not await self.can_access(student_id):
            return
        changed = await sync_to_async(db.edit_message_text)(message_id, text, self.teacher_tg_id)
        if not changed:
            return

        deliveries = await sync_to_async(db.get_deliveries)(message_id)
        for chat_id, tg_message_id in deliveries:
            try:
                await edit_telegram_text(chat_id, tg_message_id, text)
            except Exception:
                pass

        updated_row = await sync_to_async(db.get_message_by_id)(message_id)
        await self.broadcast({"type": "chat.edit", "message": message_payload(updated_row, self.teacher_tg_id, self.viewer_role)})

    async def handle_read(self, content):
        student_id = int(content["chat_id"])
        if not await self.can_access(student_id):
            return
        await sync_to_async(db.mark_messages_read)(from_user_id=student_id, to_user_id=self.teacher_tg_id)
        await self.broadcast({"type": "chat.read", "chat_id": student_id})

    @staticmethod
    def media_kind(mime_type, filename):
        mime_type = mime_type or mimetypes.guess_type(filename)[0] or ""
        if mime_type.startswith("image/"):
            return "photo"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        return "document"

    async def broadcast(self, payload):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "ws.message", "payload": payload},
        )

    async def ws_message(self, event):
        await self.send_json(event["payload"])

    @sync_to_async
    def can_access(self, student_id):
        return db.teacher_can_access_student(self.teacher_tg_id, student_id)

    @sync_to_async
    def get_dialogs(self):
        return [dialog_payload(row) for row in db.get_miniapp_dialogs(self.teacher_tg_id)]

    @sync_to_async
    def get_history(self):
        teacher = db.get_user(self.teacher_tg_id)
        viewer_role = teacher[4] if teacher else "teacher"
        return [message_payload(row, self.teacher_tg_id, viewer_role) for row in db.get_miniapp_history(self.teacher_tg_id)]
