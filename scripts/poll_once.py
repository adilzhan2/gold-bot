"""Один прогон опроса — для GitHub Actions (cron каждые 5 мин, serverless).

Фетчит фид → ищет свежие сетапы → шлёт в Telegram → дедуп через state/sent.json.
Без бесконечного цикла и без macOS-уведомлений (раннер — Linux).
Токены/ключи берутся из env (GitHub Secrets): TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID, TWELVEDATA_KEY.
"""
import json
import sys
from pathlib import Path

from goldbot.charts import render_setup
from goldbot.features.setups import generate_setups
from goldbot.live.feed import fetch
from goldbot.live.telegram import send
from goldbot.model.imitation import load_imitation, score_take
from scripts.alerter import build_signal

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "sent.json"
CHART = Path("/tmp/gold_chart.png")  # эфемерно, в репо не коммитим
FRESH_MIN = 30      # сетап свежий, если подтверждён в последние N мин (терпит дрейф cron)
KEEP_STATE = 500    # сколько последних меток хранить (чтобы файл не пух)


def load_sent() -> list[str]:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return []


def main():
    try:
        df = fetch()
    except Exception as e:  # noqa: BLE001 — сбой фида не валим красным
        print(f"feed error: {e}")
        return

    setups = generate_setups(df)
    last_t = df.index[-1]
    fresh = [s for s in setups if (last_t - s.time).total_seconds() <= FRESH_MIN * 60]

    sent = load_sent()
    sent_set = set(sent)
    clf = load_imitation()
    new = 0
    for s in fresh:
        key = str(s.time)
        if key in sent_set:
            continue
        d = "LONG" if s.direction == 1 else "SHORT"
        rr = s.features["rr_target"]
        p = score_take(clf, s)
        render_setup(df, s.bar, s.direction, s.entry, s.sl, s.tp,
                     s.zone_top, s.zone_bottom, s.sweep_bar, CHART,
                     title=f"{d}  RR {rr:.1f}" + (f"  p {p:.0%}" if p is not None else ""))
        text = build_signal(d, s, rr, p, (p is None or p >= 0.5),
                            src=df.attrs.get("ticker", "XAU/USD"))
        if send(text, CHART):
            sent.append(key)
            sent_set.add(key)
            new += 1
            print(f"sent: {d} @ {s.entry:.2f} p={p}")

    if new:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(sent[-KEEP_STATE:], indent=0))

    print(f"ok: {len(df)} баров ({df.attrs.get('ticker')}), свежих {len(fresh)}, новых алертов {new}")


if __name__ == "__main__":
    main()
