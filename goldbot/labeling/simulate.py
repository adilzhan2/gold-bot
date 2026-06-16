"""Симуляция сделки по чек-листу:

- лимитка на краю имбаланса, ждём заполнения FILL_WINDOW баров
- стоп за фитилём sweep (буфер уже включён в sl)
- на 2.5R закрываем 60%, остаток в безубыток, тянем до пула
- если до пула < 2.5R — просто полный тейк на пуле
- внутри одного бара TP и SL — консервативно считаем SL

Возвращает realized R; label = 1 если R > 0.
"""
import numpy as np
import pandas as pd

from goldbot.features.setups import SPREAD, Setup, bar_minutes

FILL_WINDOW_MIN = 120   # 2ч ждём лимитку
HOLD_MAX_MIN = 2880     # 2 суток максимум в позиции
PARTIAL_RR = 2.5        # где фиксируем часть
PARTIAL_FRAC = 0.6      # сколько фиксируем (из "50-70%")


def simulate(setup: Setup, hi: np.ndarray, lo: np.ndarray, c: np.ndarray, bm: int = 5) -> float | None:
    """None = лимитка не заполнилась (сделки не было). bm — минут в баре."""
    d, entry, sl, tp = setup.direction, setup.entry, setup.sl, setup.tp
    risk = d * (entry - sl)
    rr_tp = d * (tp - entry) / risk
    cost_r = SPREAD / risk  # спред платим один раз за цикл сделки
    n = len(c)
    fill_w = FILL_WINDOW_MIN // bm
    hold_max = HOLD_MAX_MIN // bm

    # --- ждём заполнения лимитки ---
    fill = None
    for k in range(setup.bar + 1, min(setup.bar + 1 + fill_w, n)):
        touched = lo[k] <= entry if d == 1 else hi[k] >= entry
        if touched:
            fill = k
            break
    if fill is None:
        return None

    # --- в позиции ---
    partial_done = rr_tp <= PARTIAL_RR  # близкий пул: частичная не нужна
    stop = sl
    realized = 0.0
    frac = 1.0
    end = min(fill + hold_max, n)
    for k in range(fill, end):
        hit_stop = lo[k] <= stop if d == 1 else hi[k] >= stop
        if hit_stop:
            realized += frac * d * (stop - entry) / risk
            return realized - cost_r
        if not partial_done:
            partial_px = entry + d * PARTIAL_RR * risk
            if (d == 1 and hi[k] >= partial_px) or (d == -1 and lo[k] <= partial_px):
                realized += PARTIAL_FRAC * PARTIAL_RR
                frac -= PARTIAL_FRAC
                stop = entry  # безубыток
                partial_done = True
        hit_tp = hi[k] >= tp if d == 1 else lo[k] <= tp
        if hit_tp:
            realized += frac * rr_tp
            return realized - cost_r
    # таймаут — закрываем по рынку
    realized += frac * d * (c[end - 1] - entry) / risk
    return realized - cost_r


def label_setups(setups: list[Setup], df: pd.DataFrame) -> pd.DataFrame:
    hi, lo, c = df["high"].values, df["low"].values, df["close"].values
    bm = bar_minutes(df)
    rows = []
    for s in setups:
        r = simulate(s, hi, lo, c, bm)
        if r is None:
            continue  # не заполнилась — в датасет не идёт
        rows.append({"bar": s.bar, "time": s.time, "r": r, "label": int(r > 0),
                     "entry": s.entry, "sl": s.sl, "tp": s.tp,
                     "zone_top": s.zone_top, "zone_bottom": s.zone_bottom,
                     "sweep_bar": s.sweep_bar, "sweep_px": s.sweep_px,
                     **s.features})
    return pd.DataFrame(rows)
