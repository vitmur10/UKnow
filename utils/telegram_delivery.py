"""User-facing descriptions of Telegram delivery failures."""


START_BOT_MESSAGE = (
    "Бот не може написати отримувачу. Попросіть його відкрити цього бота, "
    "натиснути /start і перевірити, що бот не заблокований."
)
GENERIC_DELIVERY_MESSAGE = "Telegram не прийняв повідомлення. Спробуйте ще раз трохи пізніше."


def is_missing_reply(description):
    text = str(description).lower()
    return (
        "replied message not found" in text
        or "message to be replied not found" in text
        or "message to reply not found" in text
        or "reply message not found" in text
    )


def delivery_error_message(description, status_code=None):
    text = str(description).lower()
    if "user is deactivated" in text:
        return "Telegram-акаунт отримувача деактивовано. Повідомлення йому недоступні."
    if (
        "bot was blocked" in text
        or "bot can't initiate conversation" in text
        or "bot can’t initiate conversation" in text
    ):
        return START_BOT_MESSAGE
    if "chat not found" in text:
        return "Telegram не знайшов чат отримувача. Перевірте його акаунт і попросіть натиснути /start у цьому боті."
    if is_missing_reply(text):
        return "Telegram не знайшов повідомлення, на яке ви відповідаєте. Надішліть текст без відповіді."
    if "message is too long" in text or "caption is too long" in text:
        return "Повідомлення завелике для Telegram. Скоротіть текст і надішліть його ще раз."
    if status_code == 429 or "retry after" in text or "retry in" in text or "too many requests" in text or "flood control" in text:
        return "Telegram тимчасово обмежив надсилання. Спробуйте ще раз трохи пізніше."
    return GENERIC_DELIVERY_MESSAGE
