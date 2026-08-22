import httpx
from django.conf import settings
from django.core.files.base import ContentFile


async def download_telegram_voice_to_message(message):
    if not message.telegram_file_id:
        return message

    async with httpx.AsyncClient(timeout=30) as client:
        file_response = await client.get(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile",
            params={"file_id": message.telegram_file_id},
        )
        file_response.raise_for_status()
        file_path = file_response.json()["result"]["file_path"]

        media_response = await client.get(
            f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}",
        )
        media_response.raise_for_status()

    filename = file_path.rsplit("/", 1)[-1]
    message.voice.save(filename, ContentFile(media_response.content), save=True)
    return message

