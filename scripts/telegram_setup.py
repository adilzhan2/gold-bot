"""Настройка Telegram-уведомлений за один проход.

Шаги:
1. В Telegram напиши @BotFather → /newbot → получи ТОКЕН.
2. Найди своего бота по имени, нажми Start и напиши ему любое сообщение.
3. Запусти:  python -m scripts.telegram_setup <ТОКЕН>
   Скрипт сам найдёт твой chat_id, сохранит конфиг и пришлёт тест.
"""
import sys

from goldbot.live.telegram import discover_chat_id, save_creds, send


def main():
    if len(sys.argv) < 2:
        print("Использование: python -m scripts.telegram_setup <ТОКЕН_БОТА>")
        print("(токен берётся у @BotFather; перед этим напиши своему боту любое сообщение)")
        sys.exit(1)

    token = sys.argv[1].strip()
    print("Ищу chat_id из твоих сообщений боту...")
    chat_id = discover_chat_id(token)
    if not chat_id:
        print("Не нашёл сообщений. Открой своего бота в Telegram, нажми Start, "
              "напиши «привет» и запусти скрипт снова.")
        sys.exit(1)

    save_creds(token, chat_id)
    print(f"chat_id = {chat_id}, конфиг сохранён в data/telegram.json")
    if send("gold-bot подключён ✅ Сюда будут падать сетапы и heartbeat."):
        print("Тестовое сообщение отправлено — проверь Telegram.")
    else:
        print("Не удалось отправить тест — проверь токен.")


if __name__ == "__main__":
    main()
