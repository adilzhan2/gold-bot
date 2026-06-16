"""Настройка OANDA-фида.

Шаги:
1. Заведи бесплатный demo (practice) аккаунт на oanda.com.
2. В разделе "Manage API Access" сгенерируй персональный токен.
3. Запусти:  python -m scripts.oanda_setup <ТОКЕН>
   Скрипт сохранит токен и проверит, что котировки XAU_USD тянутся.
"""
import sys

from goldbot.live.oanda import fetch_oanda, save_token


def main():
    if len(sys.argv) < 2:
        print("Использование: python -m scripts.oanda_setup <ТОКЕН>")
        sys.exit(1)

    save_token(sys.argv[1].strip())
    print("Токен сохранён в data/oanda.json. Проверяю котировки XAU_USD...")
    try:
        df = fetch_oanda(count=200)
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка: {e}")
        print("Проверь токен и что аккаунт — practice (демо).")
        sys.exit(1)

    print(f"OK: {len(df)} свечей XAU_USD, последняя {df.index[-1]} = {df['close'].iloc[-1]:.2f}")
    print("Фид переключён на OANDA. Перезапусти алертер (launchctl unload/load).")


if __name__ == "__main__":
    main()
