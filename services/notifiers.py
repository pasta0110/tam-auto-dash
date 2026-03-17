from __future__ import annotations

import requests


class Notifier:
    def send(self, message: str) -> bool:
        raise NotImplementedError


class NoopNotifier(Notifier):
    def send(self, message: str) -> bool:
        return False


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str, timeout: int = 10):
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.timeout = timeout

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={"chat_id": self.chat_id, "text": message, "disable_web_page_preview": True},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False


def build_telegram_notifier(token: str | None, chat_id: str | None) -> Notifier:
    if (token or "").strip() and (chat_id or "").strip():
        return TelegramNotifier(token=token or "", chat_id=chat_id or "")
    return NoopNotifier()
