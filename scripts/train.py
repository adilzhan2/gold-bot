"""Шаг 3: тренировка MLP на train-части (по времени), сохранение весов."""
import pickle
from pathlib import Path

import pandas as pd
import torch

from goldbot.features.setups import FEATURE_COLS
from goldbot.model.train import time_split, train_model

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "processed" / "dataset.parquet"
MODELS = ROOT / "models"


def main():
    dataset = pd.read_parquet(DATASET)
    cols = FEATURE_COLS

    train_df, test_df = time_split(dataset)
    print(f"train: {len(train_df)} ({train_df['time'].min()} → {train_df['time'].max()})")
    print(f"test:  {len(test_df)} ({test_df['time'].min()} → {test_df['time'].max()})")

    model, scaler = train_model(train_df, cols)

    MODELS.mkdir(exist_ok=True)
    torch.save(model.state_dict(), MODELS / "scorer.pt")
    with open(MODELS / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)
    test_df.to_parquet(MODELS / "test_set.parquet")
    print(f"Сохранил модель и test set → {MODELS}/")


if __name__ == "__main__":
    main()
