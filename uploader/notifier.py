import os
from services.notifiers import build_telegram_notifier


def notify_telegram(msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    notifier = build_telegram_notifier(token, chat_id)
    notifier.send(msg)
