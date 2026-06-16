"""Настройка Twelve Data фида.

Шаги:
1. Зайди на twelvedata.com → Sign up (бесплатно, по email).
2. В дашборде скопируй свой API key.
3. Запусти:  python -m scripts.twelvedata_setup <КЛЮЧ>
   Скрипт сохранит ключ и проверит, что котировки XAU/USD тянутся.
"""
import sys

from goldbot.live.twelvedata import fetch_td, save_key


def main():
    if len(sys.argv) < 2:
        print("Использование: python -m scripts.twelvedata_setup <API_KEY>")
        sys.exit(1)

    save_key(sys.argv[1].strip())
    print("Ключ сохранён в data/twelvedata.json. Проверяю котировки XAU/USD...")
    try:
        df = fetch_td(outputsize=200)
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка: {e}")
        print("Проверь ключ на twelvedata.com (раздел API Keys).")
        sys.exit(1)

    print(f"OK: {len(df)} свечей XAU/USD, последняя {df.index[-1]} = {df['close'].iloc[-1]:.2f}")
    print("Фид переключён на Twelve Data. Перезапусти алертер (launchctl unload/load).")


if __name__ == "__main__":
    main()
