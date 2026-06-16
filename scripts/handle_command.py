"""Обработчик ОДНОЙ команды из вебхука (repository_dispatch).

Команда приходит из Cloudflare Worker через GitHub repository_dispatch
(client_payload.cmd). В отличие от respond.py — не читает getUpdates,
а сразу выполняет переданную команду. Это даёт мгновенный отклик:
нажатие → Worker → GitHub → ответ (~1 мин), без задержек cron.

Запуск: python -m scripts.handle_command "/check"
"""
import sys

from goldbot.live.telegram import send
from scripts.respond import COMMANDS, HELP


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower().split("@")[0]
    fn = COMMANDS.get(cmd)
    if fn:
        fn()
        print(f"выполнил команду: {cmd}")
    elif cmd.startswith("/"):
        send(HELP)
        print(f"неизвестная команда {cmd} → отправил help")
    else:
        print(f"не команда, игнор: {cmd!r}")


if __name__ == "__main__":
    main()
