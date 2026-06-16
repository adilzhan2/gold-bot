"""Triple-barrier разметка: для каждого сетапа смотрим вперёд —
что случилось раньше: TP (label=1), SL (label=0) или таймаут (label=0).

Разметка СМОТРИТ В БУДУЩЕЕ — и это нормально: это y (ответ),
а не X (фичи). В проде модель будущего не видит, она видит только фичи.
"""
import numpy as np
import pandas as pd

# Спред на XAUUSD: ~0.2-0.4$ у нормальных брокеров. Закладываем честно.
SPREAD = 0.35


def label_setups(
    df: pd.DataFrame,
    setup_mask: np.ndarray,
    direction: int,  # +1 long, -1 short
    atr_: np.ndarray,
    tp_atr: float = 2.0,
    sl_atr: float = 1.0,
    horizon: int = 48,  # 48 баров m5 = 4 часа
    spread: float = SPREAD,
) -> pd.DataFrame:
    """Возвращает DataFrame: индекс бара входа, label, R-результат."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    rows = []
    for i in np.flatnonzero(setup_mask):
        a = atr_[i]
        if np.isnan(a) or a <= 0 or i + 1 >= n:
            continue
        # вход по рынку на закрытии бара сетапа, спред платим сразу
        entry = close[i] + direction * spread / 2
        tp = entry + direction * tp_atr * a
        sl = entry - direction * sl_atr * a

        label, r = 0, 0.0
        end = min(i + 1 + horizon, n)
        for k in range(i + 1, end):
            hit_tp = high[k] >= tp if direction == 1 else low[k] <= tp
            hit_sl = low[k] <= sl if direction == 1 else high[k] >= sl
            if hit_sl:  # консервативно: если оба в одном баре — считаем SL
                label, r = 0, -sl_atr
                break
            if hit_tp:
                label, r = 1, tp_atr
                break
        else:
            # таймаут: закрываем по рынку, платим спред на выходе
            exit_px = close[end - 1] - direction * spread / 2
            r = direction * (exit_px - entry) / a
            label = int(r > 0)

        rows.append({"bar": i, "time": df.index[i], "direction": direction, "label": label, "r": r})

    return pd.DataFrame(rows)
