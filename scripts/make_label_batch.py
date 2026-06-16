"""Готовит батч для разметки: сэмплирует сетапы из датасета (стратифицировано
по годам), рендерит каждый в PNG и пишет очередь data/labels/queue.csv.

Исход сделки (r) сохраняется в очереди, но на картинке его НЕТ —
размечаешь так, как видел бы вживую.
"""
from pathlib import Path

import pandas as pd

from goldbot.charts import render_setup
from goldbot.data.loader import load_candles

ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = ROOT / "data" / "labels"
IMG_DIR = LABELS_DIR / "img"
BATCH = 400  # сколько сетапов на разметку


def main():
    ds = pd.read_parquet(ROOT / "data" / "processed" / "dataset.parquet")
    ds["year"] = pd.to_datetime(ds["time"]).dt.year

    # стратифицируем по годам, чтобы не размечать один режим рынка
    per_year = max(BATCH // ds["year"].nunique(), 1)
    sample = (
        ds.groupby("year", group_keys=False)
        .apply(lambda g: g.sample(min(per_year, len(g)), random_state=42), include_groups=False)
        .sort_values("time")
        .reset_index(drop=True)
    )

    sample["id"] = sample.index
    sample.to_csv(LABELS_DIR / "queue.csv", index=False)  # фичи рядом с id

    print(f"Рендерю {len(sample)} сетапов (уже готовые пропускаю)...")
    df = load_candles()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for i, row in sample.iterrows():
        out = IMG_DIR / f"{i}.png"
        if out.exists():  # сэмпл воспроизводим → картинка та же, метки валидны
            continue
        d = "LONG" if row["direction"] == 1 else "SHORT"
        rr = row["rr_target"]
        render_setup(
            df,
            bar=int(row["bar"]),
            direction=int(row["direction"]),
            entry=row["entry"],
            sl=row["sl"],
            tp=row["tp"],
            zone_top=row["zone_top"],
            zone_bottom=row["zone_bottom"],
            sweep_bar=int(row["sweep_bar"]),
            out_path=IMG_DIR / f"{i}.png",
            title=f"#{i}  {d}  RR до цели {rr:.1f}",
        )
        if i % 50 == 0:
            print(f"  {i}/{len(sample)}")

    print(f"Готово: {len(sample)} картинок в {IMG_DIR}")
    print("Дальше: python -m scripts.label_app и открой http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
