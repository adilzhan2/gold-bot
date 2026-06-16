"""Live-алертер: поллит котировки раз в минуту, гонит тот же state machine,
что и бэктест, и на свежий сетап шлёт уведомление macOS (+ Telegram, если
заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID).

Каждый алерт сохраняется с картинкой в data/alerts/ — потом размечаешь
его в label_app так же, как исторические (это и есть сбор твоего датасета).

Запуск:  python -m scripts.alerter
"""
import csv
import subprocess
import time
from pathlib import Path

import pandas as pd

from goldbot.charts import render_setup
from goldbot.features.setups import generate_setups
from goldbot.live.feed import fetch
from goldbot.live.telegram import send as notify_telegram
from goldbot.model.imitation import load_imitation, score_take

ROOT = Path(__file__).resolve().parents[1]
ALERTS_DIR = ROOT / "data" / "alerts"
LOG = ALERTS_DIR / "alerts.csv"
POLL_SEC = 180            # раз в 3 мин — меньше дёргаем Yahoo, реже рейт-лимит
FRESH_BARS = 30           # сетап свежий, если подтверждён в последних N мин (вход лимиткой ещё актуален)
SEND_ALL = True           # режим теста: слать ВСЕ сетапы с вердиктом модели
MIN_TAKE_PROB = 0.5       # порог «вкуса» (используется только если SEND_ALL=False)
FAIL_ALERT_AFTER = 10     # «бот ослеп» только при долгом простое (~30 мин), не на мигании


def notify_mac(text: str):
    subprocess.run(
        ["osascript", "-e", f'display notification "{text}" with title "gold-bot"'],
        check=False,
    )


def build_signal(d: str, s, rr: float, p, take_ok: bool, src: str = "XAU/USD спот") -> str:
    """Actionable-сигнал для Telegram с КОНКРЕТНЫМИ ценами Entry/SL/TP.
    Фид теперь спот XAU/USD — цены совпадают с TradingView/Exness,
    уровни можно вписывать напрямую."""
    head = "🟢 ПОКУПАЙ XAUUSD" if d == "LONG" else "🔴 ПРОДАВАЙ XAUUSD"
    sl_dist = abs(s.entry - s.sl)
    tp_dist = abs(s.tp - s.entry)
    verdict = ""
    if p is not None:
        mark = "✅ в твоём стиле" if take_ok else "⚠️ модель бы пропустила"
        verdict = f"\nМодель p(взял): {p:.0%}  {mark}"
    return (
        f"{head}\n"
        f"Вход: {s.entry:.2f}\n"
        f"🛑 Stop Loss: {s.sl:.2f}   (−${sl_dist:.1f})\n"
        f"🎯 Take Profit: {s.tp:.2f}   (+${tp_dist:.1f}, RR {rr:.1f})"
        f"{verdict}\n"
        f"⏱ {s.time:%H:%M} UTC · {src}"
    )


def main():
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if LOG.exists():
        seen = set(pd.read_csv(LOG)["time"].astype(str))

    clf = load_imitation()
    if SEND_ALL:
        print("Режим теста: шлю ВСЕ сетапы с вердиктом модели.")
    elif clf is None:
        print("Имитационной модели нет — шлю все сетапы (фильтра вкуса нет).")
    else:
        print(f"Фильтр вкуса включён: уведомление только при p(взял) >= {MIN_TAKE_PROB}.")
    print(f"Алертер запущен, полл каждые {POLL_SEC}с. Ctrl+C для остановки.")

    fails = 0          # сбоев фида подряд
    blind_alerted = False  # уже предупредили, что бот ослеп — не спамим
    while True:
        try:
            df = fetch()
            setups = generate_setups(df)
            fresh = [s for s in setups
                     if s.bar >= len(df) - FRESH_BARS and str(s.time) not in seen]
            sent = 0
            for s in fresh:
                d = "LONG" if s.direction == 1 else "SHORT"
                rr = s.features["rr_target"]
                p = score_take(clf, s)  # None если модели нет
                take_ok = p is None or p >= MIN_TAKE_PROB

                # картинку и лог пишем для ВСЕХ свежих — разметка должна копиться
                png = ALERTS_DIR / f"{s.time:%Y%m%d_%H%M}.png"
                ptxt = f" | p(взял) {p:.0%}" if p is not None else ""
                render_setup(df, s.bar, s.direction, s.entry, s.sl, s.tp,
                             s.zone_top, s.zone_bottom, s.sweep_bar, png,
                             title=f"LIVE {d}  RR {rr:.1f}{ptxt}")
                new = not LOG.exists()
                with open(LOG, "a", newline="") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(["time", "direction", "entry", "sl", "tp", "rr",
                                    "p_take", "alerted", "png"])
                    w.writerow([s.time, s.direction, s.entry, s.sl, s.tp, round(rr, 2),
                                round(p, 3) if p is not None else "",
                                int(take_ok or SEND_ALL), png.name])
                seen.add(str(s.time))

                # уведомление: в режиме теста — все, иначе только прошедшие фильтр
                if take_ok or SEND_ALL:
                    text = build_signal(d, s, rr, p, take_ok, src=df.attrs.get("ticker", "XAU/USD"))
                    notify_mac(f"{'ПОКУПАЙ' if s.direction==1 else 'ПРОДАВАЙ'} XAUUSD"
                               f" — модель {p:.0%}" if p is not None else text.split(chr(10))[0])
                    notify_telegram(text, png)
                    sent += 1
                    print(f"[ALERT] {d} @ {s.entry:.2f} p={p:.0%}" if p is not None
                          else f"[ALERT] {d} @ {s.entry:.2f}")
                else:
                    print(f"[skip p={p:.0%}] {d} @ {s.entry:.2f} — не твой вкус")
            now = pd.Timestamp.now(tz="UTC")
            print(f"{now:%H:%M:%S} ok: {len(df)} баров ({df.attrs.get('ticker')}), "
                  f"в окне: {len(setups)}, свежих: {len(fresh)}, отправлено: {sent}")

            # фид жив — если до этого ослеп, сообщаем что прозрел
            if blind_alerted:
                notify_mac("Снова вижу рынок — фид восстановился")
                notify_telegram("gold-bot: фид восстановился ✅", None)
                print("[HEARTBEAT] фид восстановился")
            fails, blind_alerted = 0, False
        except Exception as e:  # noqa: BLE001 — алертер не должен умирать
            fails += 1
            print(f"ошибка полла ({fails} подряд): {e}")
            # ослеп: предупреждаем один раз, пока не восстановится
            if fails >= FAIL_ALERT_AFTER and not blind_alerted:
                msg = f"Бот ослеп: фид не отвечает {fails} циклов подряд"
                notify_mac(msg)
                notify_telegram(f"gold-bot: ⚠️ {msg}", None)
                blind_alerted = True
                print(f"[HEARTBEAT] {msg}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
