"""Telegram-уведомления: токен и chat_id берём из data/telegram.json
(или из env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — env приоритетнее).

Конфиг-файл удобнее env, потому что служба launchd своего окружения
почти не имеет — а файл она прочитает.
"""
import json
import os
from pathlib import Path

import requests

CONFIG = Path(__file__).resolve().parents[2] / "data" / "telegram.json"


def load_creds() -> tuple[str | None, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        return token, chat
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text())
        return cfg.get("token"), str(cfg.get("chat_id")) if cfg.get("chat_id") else None
    return None, None


def save_creds(token: str, chat_id: str):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"token": token, "chat_id": chat_id}, indent=2))


def send(text: str, png: Path | None = None) -> bool:
    """Шлёт текст (или фото с подписью). True если ушло."""
    token, chat = load_creds()
    if not token or not chat:
        return False
    try:
        if png is not None:
            with open(png, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat, "caption": text},
                    files={"photo": f},
                    timeout=15,
                )
        else:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat, "text": text},
                timeout=15,
            )
        return r.ok
    except Exception as e:  # noqa: BLE001 — телеграм не должен ронять алертер
        print(f"telegram error: {e}")
        return False


def discover_chat_id(token: str) -> str | None:
    """Берёт chat_id из последнего сообщения боту (getUpdates).
    Перед вызовом напиши боту любое сообщение в Telegram."""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
    updates = r.json().get("result", [])
    for u in reversed(updates):
        msg = u.get("message") or u.get("my_chat_member") or {}
        chat = msg.get("chat", {})
        if chat.get("id"):
            return str(chat["id"])
    return None
