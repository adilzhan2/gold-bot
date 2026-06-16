"""Обработчик команд Telegram (serverless, запускается каждые ~5 мин).

Читает входящие сообщения боту и отвечает:
  /check (/now)  — проверить рынок ПРЯМО СЕЙЧАС и дать вердикт
  /last          — последний отправленный сигнал
  /status        — бот жив? цена, сколько баров
  /week (/stats) — сводка за 7 дней (активность + вердикты модели)
  /help          — список команд

Плюс авто-сводка раз в неделю (понедельник).

Ответ приходит в течение интервала воркера (~5 мин) — бот serverless,
постоянного сервера нет.
"""
import json
from pathlib import Path

import pandas as pd

from goldbot.charts import render_setup
from goldbot.features.setups import generate_setups
from goldbot.live import twelvedata
from goldbot.live.telegram import get_updates, send
from goldbot.model.imitation import load_imitation, score_take
from scripts.alerter import build_signal

ROOT = Path(__file__).resolve().parents[1]
OFFSET_F = ROOT / "state" / "tg_offset.txt"
WEEK_F = ROOT / "state" / "last_week.txt"
ALERTS_CSV = ROOT / "state" / "alerts.csv"
CHART = Path("/tmp/check.png")

HELP = ("Команды:\n"
        "/check — проверить рынок сейчас и дать вердикт\n"
        "/last — последний сигнал\n"
        "/status — бот жив? цена\n"
        "/week — сводка за 7 дней")


def _verdict_mark(p):
    if p is None:
        return ""
    return " ✅ в твоём стиле" if p >= 0.5 else " ⚠️ модель бы пропустила"


def handle_check():
    df = twelvedata.fetch_td()  # один запрос (дёшево, для on-demand хватает)
    setups = generate_setups(df)
    clf = load_imitation()
    price = df["close"].iloc[-1]
    t = df.index[-1]
    if not setups:
        send(f"🔍 Проверил сейчас — валидного сетапа по чек-листу НЕТ.\n"
             f"XAU/USD {price:.2f} ({t:%H:%M} UTC). Продолжаю следить.")
        return
    s = setups[-1]
    d = "LONG" if s.direction == 1 else "SHORT"
    rr = s.features["rr_target"]
    p = score_take(clf, s)
    age_h = (t - s.time).total_seconds() / 3600
    render_setup(df, s.bar, s.direction, s.entry, s.sl, s.tp,
                 s.zone_top, s.zone_bottom, s.sweep_bar, CHART,
                 title=f"{d}  RR {rr:.1f}" + (f"  p {p:.0%}" if p is not None else ""))
    note = "" if age_h <= 0.5 else f"\n⚠️ сетап {age_h:.1f}ч назад — проверь актуальность"
    send("🔍 Проверка сейчас:\n" +
         build_signal(d, s, rr, p, (p is None or p >= 0.5), src=df.attrs.get("ticker")) + note,
         CHART)


def handle_last():
    if not ALERTS_CSV.exists() or pd.read_csv(ALERTS_CSV).empty:
        send("Сигналов ещё не было.")
        return
    a = pd.read_csv(ALERTS_CSV).iloc[-1]
    d = "LONG" if a["direction"] == 1 else "SHORT"
    p = a["p_take"]
    pm = f"{float(p):.0%}{_verdict_mark(float(p))}" if str(p) not in ("", "nan") else "—"
    send(f"Последний сигнал:\n{d} XAU/USD\nВход {a['entry']} | SL {a['sl']} | TP {a['tp']} "
         f"(RR {a['rr']})\nМодель: {pm}\n{str(a['time'])[:16]} UTC")


def handle_status():
    try:
        df = twelvedata.fetch_td()
        send(f"✅ Бот жив. XAU/USD {df['close'].iloc[-1]:.2f}, "
             f"{len(df)} баров, посл. свеча {df.index[-1]:%H:%M} UTC.")
    except Exception as e:  # noqa: BLE001
        send(f"⚠️ Бот отвечает, но фид сбоит: {e}")


def _week_summary(days: int = 7) -> str:
    if not ALERTS_CSV.exists():
        return "За неделю сигналов не было."
    a = pd.read_csv(ALERTS_CSV)
    a["time"] = pd.to_datetime(a["time"], utc=True)
    cutoff = a["time"].max() - pd.Timedelta(days=days)
    wk = a[a["time"] >= cutoff]
    if wk.empty:
        return f"За {days} дней сигналов не было. Бот следит."
    p = pd.to_numeric(wk["p_take"], errors="coerce")
    take = int((p >= 0.5).sum())
    skip = int((p < 0.5).sum())
    return (f"📊 Сводка за {days} дней:\n"
            f"сигналов: {len(wk)}\n"
            f"модель ✅ брала: {take}\n"
            f"модель ⚠️ пропускала: {skip}\n"
            f"(исходы win/loss веди в журнале — /help)")


def handle_week():
    send(_week_summary())


COMMANDS = {
    "/check": handle_check, "/now": handle_check,
    "/last": handle_last, "/status": handle_status,
    "/week": handle_week, "/stats": handle_week,
    "/help": lambda: send(HELP), "/start": lambda: send("Привет! " + HELP),
}


def auto_weekly():
    """Раз в неделю (по ISO-неделе) шлёт сводку сам."""
    cur = pd.Timestamp.utcnow().strftime("%G-W%V")
    last = WEEK_F.read_text().strip() if WEEK_F.exists() else ""
    if cur != last:
        send(_week_summary())
        WEEK_F.parent.mkdir(parents=True, exist_ok=True)
        WEEK_F.write_text(cur)


def main():
    offset = int(OFFSET_F.read_text()) if OFFSET_F.exists() else None
    updates = get_updates(offset)
    last_id = offset
    for u in updates:
        last_id = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message") or {}
        text = (msg.get("text") or "").strip().lower().split("@")[0]
        fn = COMMANDS.get(text)
        if fn:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                send(f"ошибка команды {text}: {e}")
        elif text.startswith("/"):
            send(HELP)

    if last_id is not None and last_id != offset:
        OFFSET_F.parent.mkdir(parents=True, exist_ok=True)
        OFFSET_F.write_text(str(last_id))

    auto_weekly()
    print(f"updates обработано: {len(updates)}")


if __name__ == "__main__":
    main()
