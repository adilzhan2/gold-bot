"""Тренировка с walk-forward: учимся на прошлом, проверяем на будущем.

Модель — РЕГРЕССИЯ: предсказывает ожидаемый R сделки, а не вероятность
выигрыша. Так сделка +6R и сделка +1.5R перестают быть одинаковой "1",
и порог отбора становится осмысленным: торгуем, если ожидаемый R > 0.

НИКОГДА не random split по времени — модель "подсмотрит" будущее
через соседние бары, и метрики будут красивой ложью.
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler

from goldbot.model.mlp import SetupScorer

R_CLIP = (-2.0, 8.0)  # обрезаем хвосты: один лаки-раннер +40R не должен рулить лоссом


def time_split(dataset: pd.DataFrame, test_frac: float = 0.25):
    """Хронологический сплит: последние test_frac по времени — в тест."""
    ds = dataset.sort_values("time").reset_index(drop=True)
    cut = int(len(ds) * (1 - test_frac))
    return ds.iloc[:cut], ds.iloc[cut:]


def _val_metrics(pred: np.ndarray, r: np.ndarray) -> tuple[float, float]:
    """(корреляция предсказания с фактом, avg R сделок с pred > 0)."""
    corr = float(np.corrcoef(pred, r)[0, 1]) if pred.std() > 1e-9 else 0.0
    taken = r[pred > 0]
    avg_r = float(taken.mean()) if len(taken) else float("nan")
    return corr, avg_r


def train_model(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    epochs: int = 200,
    lr: float = 1e-3,
    seed: int = 42,
):
    torch.manual_seed(seed)
    np.random.seed(seed)

    X = train_df[feature_cols].fillna(0).values.astype(np.float32)
    y = train_df["r"].clip(*R_CLIP).values.astype(np.float32)

    scaler = StandardScaler().fit(X)
    X = scaler.transform(X).astype(np.float32)

    # валидация — последние 20% train ПО ВРЕМЕНИ (опять же не random)
    cut = int(len(X) * 0.8)
    Xt, yt = torch.tensor(X[:cut]), torch.tensor(y[:cut])
    Xv, yv = torch.tensor(X[cut:]), torch.tensor(y[cut:])

    model = SetupScorer(n_features=len(feature_cols))
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.SmoothL1Loss()  # Huber: устойчив к выбросам R

    best_corr, best_state = -1.0, None
    for epoch in range(epochs):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(Xt), yt)
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            val_p = model(Xv).numpy()
        corr, avg_r = _val_metrics(val_p, yv.numpy())
        if corr > best_corr:
            best_corr, best_state = corr, {k: v.clone() for k, v in model.state_dict().items()}
        if epoch % 20 == 0:
            n_taken = int((val_p > 0).sum())
            print(f"epoch {epoch:3d}  loss {loss.item():.4f}  val corr {corr:+.3f}  "
                  f"val avg R(pred>0) {avg_r:+.3f} ({n_taken} сделок)")

    if best_state:
        model.load_state_dict(best_state)
    print(f"best val corr: {best_corr:+.3f}  (0 = шум; >0.1 уже интересно)")
    return model, scaler


def predict(model, scaler, df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    """Возвращает предсказанный R (не вероятность)."""
    X = scaler.transform(df[feature_cols].fillna(0).values.astype(np.float32)).astype(np.float32)
    model.eval()
    with torch.no_grad():
        return model(torch.tensor(X)).numpy()
