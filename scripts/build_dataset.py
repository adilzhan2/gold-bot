"""Шаг 2: свечи → сетапы по чек-листу → симуляция сделок → датасет."""
from pathlib import Path

from goldbot.data.loader import load_candles
from goldbot.features.setups import generate_setups
from goldbot.labeling.simulate import label_setups

OUT = Path(__file__).resolve().parents[1] / "data" / "processed" / "dataset.parquet"


def main():
    print("Читаю свечи...")
    df = load_candles()
    print(f"{len(df)} баров: {df.index[0]} → {df.index[-1]}")

    print("Ищу сетапы (touch → sweep → CHoCH → имбаланс)...")
    setups = generate_setups(df)
    print(f"сетапов с целью по ликвидности: {len(setups)}")

    print("Симулирую сделки (лимитка, частичная фиксация, безубыток)...")
    dataset = label_setups(setups, df)
    filled = len(dataset)
    print(f"лимитка заполнилась: {filled}/{len(setups)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(OUT)
    print(f"Сохранил → {OUT}")
    if filled:
        print(f"Без модели: winrate {dataset['label'].mean():.1%}, "
              f"total {dataset['r'].sum():+.1f}R, avg {dataset['r'].mean():+.3f}R")


if __name__ == "__main__":
    main()
