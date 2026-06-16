"""Шаг 4: бэктест на out-of-sample (модель этих данных не видела)."""
import pickle
from pathlib import Path

import pandas as pd
import torch

from goldbot.features.setups import FEATURE_COLS
from goldbot.model.mlp import SetupScorer
from goldbot.model.train import predict
from goldbot.backtest.engine import run_backtest

MODELS = Path(__file__).resolve().parents[1] / "models"


def main():
    cols = FEATURE_COLS
    test_df = pd.read_parquet(MODELS / "test_set.parquet")

    model = SetupScorer(n_features=len(cols))
    model.load_state_dict(torch.load(MODELS / "scorer.pt", weights_only=True))
    with open(MODELS / "scaler.pkl", "rb") as f:
        scaler = pickle.load(f)

    scores = predict(model, scaler, test_df, cols)  # предсказанный R
    print("\n--- Out-of-sample бэктест (порог = ожидаемый R) ---")
    for thr in (0.0, 0.25, 0.5):
        print(f"\nожидаемый R >= {thr}:")
        run_backtest(test_df, scores, threshold=thr)


if __name__ == "__main__":
    main()
