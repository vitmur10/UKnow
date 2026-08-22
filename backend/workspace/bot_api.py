import httpx
from django.conf import settings


async def send_text_to_student(student_id: int, text: str) -> int | None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={"chat_id": student_id, "text": text},
        )
        response.raise_for_status()
    return response.json().get("result", {}).get("message_id")


async def send_voice_to_student(student_id: int, voice_path: str) -> int | None:
    async with httpx.AsyncClient(timeout=60) as client:
        with open(voice_path, "rb") as voice_file:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVoice",
                data={"chat_id": str(student_id)},
                files={"voice": voice_file},
            )
        response.raise_for_status()
    return response.json().get("result", {}).get("message_id")


async def send_attachment_to_student(
    student_id: int,
    file_path: str,
    kind: str,
    caption: str = "",
    reply_to_message_id: int | None = None,
) -> int | None:
    method_by_kind = {
        "photo": ("sendPhoto", "photo"),
        "video": ("sendVideo", "video"),
        "audio": ("sendAudio", "audio"),
        "document": ("sendDocument", "document"),
    }
    method, field_name = method_by_kind.get(kind, ("sendDocument", "document"))
    data = {"chat_id": str(student_id)}
    if caption:
        data["caption"] = caption
    if reply_to_message_id:
        data["reply_to_message_id"] = str(reply_to_message_id)
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as media_file:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}",
                data=data,
                files={field_name: media_file},
            )
        response.raise_for_status()
    return response.json().get("result", {}).get("message_id")


async def edit_telegram_text(chat_id: int, message_id: int, text: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
        )
        response.raise_for_status()


async def delete_telegram_message(chat_id: int, message_id: int):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
        )
        response.raise_for_status()
