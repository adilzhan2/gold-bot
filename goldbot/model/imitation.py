"""Загрузка и применение имитационной модели («взял бы / пропустил»).

p_take близко к 1 → сетап в твоём вкусе; близко к 0 → ты бы его слил.

Две формы модели:
  • models/imitation.json — веса (coef/scaler) для скоринга на чистом numpy.
    Не требует sklearn → лёгкий деплой на GitHub Actions. Приоритетна.
  • models/imitation.pkl — sklearn-пайплайн (фолбэк, нужен для обучения локально).

Если модели нет — score_take возвращает None (алертер не фильтрует).
"""
import json
import pickle
from pathlib import Path

import numpy as np

from goldbot.features.setups import FEATURE_COLS, Setup

MODELS = Path(__file__).resolve().parents[2] / "models"
PKL_PATH = MODELS / "imitation.pkl"
JSON_PATH = MODELS / "imitation.json"


class _JsonModel:
    """Логистическая регрессия из JSON: sigmoid(((x-mean)/scale)·coef + b)."""

    def __init__(self, d: dict):
        self.features = d["features"]
        self.mean = np.array(d["mean"], dtype=float)
        self.scale = np.array(d["scale"], dtype=float)
        self.coef = np.array(d["coef"], dtype=float)
        self.intercept = float(d["intercept"])

    def proba(self, x: np.ndarray) -> float:
        z = float(((x - self.mean) / self.scale) @ self.coef + self.intercept)
        return 1.0 / (1.0 + np.exp(-z))


def export_json(clf, path: Path = JSON_PATH):
    """Сохраняет sklearn-пайплайн как JSON для numpy-скоринга."""
    sc = clf.named_steps["standardscaler"]
    lr = clf.named_steps["logisticregression"]
    path.write_text(json.dumps({
        "features": FEATURE_COLS,
        "mean": sc.mean_.tolist(),
        "scale": sc.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
    }, indent=2))


def load_imitation():
    if JSON_PATH.exists():
        return _JsonModel(json.loads(JSON_PATH.read_text()))
    if PKL_PATH.exists():
        with open(PKL_PATH, "rb") as f:
            return pickle.load(f)
    return None


def score_take(clf, setup: Setup) -> float | None:
    """Вероятность, что ты бы взял этот сетап (0..1), или None если нет модели."""
    if clf is None:
        return None
    x = np.nan_to_num(np.array([setup.features.get(c, 0.0) for c in FEATURE_COLS], dtype=float))
    if isinstance(clf, _JsonModel):
        return clf.proba(x)
    return float(clf.predict_proba(x[None, :])[0, 1])
