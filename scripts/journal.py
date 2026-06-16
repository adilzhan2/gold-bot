"""Журнал сделок: сверяем вердикт модели с реальным исходом.

Идея: модель к каждому сетапу говорит ✅ (взял бы, p≥0.5) или ⚠️ (пропустила).
Ты отмечаешь, чем сделка кончилась. Через 10-15 записей видно, реально ли
✅-сетапы отрабатывают лучше ⚠️ — то есть есть ли от модели польза.

Использование:
  python -m scripts.journal              # список алертов + статистика
  python -m scripts.journal 2 loss       # алерт №2 — стоп (минус)
  python -m scripts.journal 2 win 35.9   # алерт №2 — тейк, +$35.9
  python -m scripts.journal 2 skip       # я этот пропустил
  python -m scripts.journal 2 loss -2.46 # минус с точной суммой
"""
import csv
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERTS = ROOT / "data" / "alerts" / "alerts.csv"
JOURNAL = ROOT / "data" / "journal.csv"
TAKE_THR = 0.5  # p≥ → модель сказала «бери»


def load_journal() -> pd.DataFrame:
    if JOURNAL.exists():
        return pd.read_csv(JOURNAL)
    return pd.DataFrame(columns=["time", "direction", "p_take", "verdict", "outcome", "usd"])


def verdict_of(p) -> str:
    if pd.isna(p) or p == "":
        return "—"
    return "✅ взял бы" if float(p) >= TAKE_THR else "⚠️ пропустила"


def show(alerts: pd.DataFrame, jrn: pd.DataFrame):
    done = set(jrn["time"].astype(str))
    print("\n=== АЛЕРТЫ (№ — для записи исхода) ===")
    for i, row in alerts.reset_index(drop=True).iterrows():
        d = "LONG " if row["direction"] == 1 else "SHORT"
        p = row["p_take"]
        mark = "✔ записан" if str(row["time"]) in done else "… ждёт исхода"
        ptxt = f"{float(p):.0%}" if p not in ("", None) and not pd.isna(p) else "—"
        print(f"  [{i+1}] {str(row['time'])[:16]}  {d}  модель {ptxt} {verdict_of(p)}  → {mark}")

    if jrn.empty:
        print("\nЖурнал пуст. Отметь исход: python -m scripts.journal <№> <win|loss|skip> [$]")
        return

    print("\n=== СТАТИСТИКА: вердикт модели → исход ===")
    traded = jrn[jrn["outcome"].isin(["win", "loss"])]
    for label, grp in (("✅ модель брала", traded[traded["verdict"] == "take"]),
                       ("⚠️ модель пропускала", traded[traded["verdict"] == "skip"])):
        n = len(grp)
        if n == 0:
            print(f"  {label}: пока нет сделок")
            continue
        wins = (grp["outcome"] == "win").sum()
        usd = pd.to_numeric(grp["usd"], errors="coerce").fillna(0).sum()
        print(f"  {label}: {n} сделок | winrate {wins/n:.0%} | итог {usd:+.2f}$")
    print("\n  Если у ✅ winrate заметно выше ⚠️ — модель ловит твой эдж.")


def main():
    if not ALERTS.exists():
        print("Пока нет алертов (data/alerts/alerts.csv).")
        return
    alerts = pd.read_csv(ALERTS).reset_index(drop=True)
    jrn = load_journal()

    if len(sys.argv) < 3:
        show(alerts, jrn)
        return

    idx = int(sys.argv[1]) - 1
    outcome = sys.argv[2].lower()
    usd = sys.argv[3] if len(sys.argv) > 3 else ""
    if idx < 0 or idx >= len(alerts):
        print(f"Нет алерта №{idx+1}. Доступно 1..{len(alerts)}.")
        return
    if outcome not in ("win", "loss", "skip"):
        print("Исход: win | loss | skip")
        return

    row = alerts.iloc[idx]
    p = row["p_take"]
    verdict = "take" if (p not in ("", None) and not pd.isna(p) and float(p) >= TAKE_THR) else "skip"

    # перезаписываем, если этот алерт уже был записан
    jrn = jrn[jrn["time"].astype(str) != str(row["time"])]
    new = pd.DataFrame([{
        "time": row["time"], "direction": int(row["direction"]),
        "p_take": p, "verdict": verdict, "outcome": outcome, "usd": usd,
    }])
    jrn = pd.concat([jrn, new], ignore_index=True)
    jrn.to_csv(JOURNAL, index=False)
    print(f"Записал: алерт №{idx+1} → {outcome} {f'({usd}$)' if usd else ''}")
    show(alerts, jrn)


if __name__ == "__main__":
    main()
