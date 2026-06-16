"""Старшие таймфреймы: зоны интереса (OB + имбаланс) и пулы ликвидности.

Зона интереса = Order Block (последняя контр-свеча перед импульсом),
у которого импульс оставил FVG — подтверждение крупного объёма.

Пул ликвидности = равные хаи/лои (equal highs/lows) — туда целимся тейком.

Всё с честным временем доступности (available_from): зона/пул "появляются"
только после закрытия подтверждающей свечи старшего ТФ.
"""
from dataclasses import dataclass

import pandas as pd

from goldbot.features.smc import atr

TF_RULES = {"30m": "30min", "1h": "1h", "4h": "4h"}
TF_DELTAS = {"30m": pd.Timedelta("30min"), "1h": pd.Timedelta("1h"), "4h": pd.Timedelta("4h")}
POOL_TOL_ATR = 0.25  # насколько "равными" должны быть хаи/лои (в ATR своего ТФ)
SWING_K = 3


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


@dataclass
class Zone:
    kind: int  # +1 бычья (лонг от неё), -1 медвежья
    top: float
    bottom: float
    tf: str
    available_from: pd.Timestamp


@dataclass
class Pool:
    kind: int  # +1 равные хаи (ликвидность СВЕРХУ), -1 равные лои
    level: float
    tf: str
    available_from: pd.Timestamp


def find_zones(h: pd.DataFrame, tf: str) -> list[Zone]:
    """OB + имбаланс: контр-свеча i, импульс к i+2 пробивает её экстремум
    и оставляет FVG между i и i+2."""
    o, hi, lo, c = h["open"].values, h["high"].values, h["low"].values, h["close"].values
    idx = h.index
    delta = TF_DELTAS[tf]
    zones = []
    for i in range(len(h) - 2):
        # бычий OB: медвежья свеча + бычий FVG сразу за ней + импульс телом выше её хая
        if c[i] < o[i] and lo[i + 2] > hi[i] and c[i + 2] > hi[i]:
            zones.append(Zone(+1, hi[i], lo[i], tf, idx[i + 2] + delta))
        # медвежий OB зеркально
        if c[i] > o[i] and hi[i + 2] < lo[i] and c[i + 2] < lo[i]:
            zones.append(Zone(-1, hi[i], lo[i], tf, idx[i + 2] + delta))
    return zones


def find_pools(h: pd.DataFrame, tf: str) -> list[Pool]:
    """Равные хаи/лои: два подтверждённых свинга на одном уровне (± tol)."""
    hi, lo = h["high"].values, h["low"].values
    idx = h.index
    delta = TF_DELTAS[tf]
    a = atr(h).values
    k = SWING_K

    swing_h, swing_l = [], []  # (bar, price)
    pools = []
    for j in range(k, len(h) - k):
        confirm_t = idx[j + k] + delta  # свинг известен через k баров
        tol = (a[j] if a[j] == a[j] else 0) * POOL_TOL_ATR
        if hi[j] == hi[j - k : j + k + 1].max() and (hi[j - k : j + k + 1] == hi[j]).sum() == 1:
            for jb, pb in swing_h[-8:]:
                if j - jb >= 2 and abs(hi[j] - pb) <= tol:
                    pools.append(Pool(+1, max(hi[j], pb), tf, confirm_t))
                    break
            swing_h.append((j, hi[j]))
        if lo[j] == lo[j - k : j + k + 1].min() and (lo[j - k : j + k + 1] == lo[j]).sum() == 1:
            for jb, pb in swing_l[-8:]:
                if j - jb >= 2 and abs(lo[j] - pb) <= tol:
                    pools.append(Pool(-1, min(lo[j], pb), tf, confirm_t))
                    break
            swing_l.append((j, lo[j]))
    return pools


def trend_series(h: pd.DataFrame, tf: str) -> list[tuple[pd.Timestamp, int]]:
    """Order Flow на HTF: +1 бычий / -1 медвежий по сломам структуры.

    Свинг подтверждается через K баров; BOS = закрытие за подтверждённый
    свинг. Возвращает моменты смены тренда (когда это стало известно).
    """
    hi, lo, c = h["high"].values, h["low"].values, h["close"].values
    idx = h.index
    delta = TF_DELTAS[tf]
    k = SWING_K

    last_sh = last_sl = float("nan")
    trend = 0
    changes = []
    for i in range(len(h)):
        j = i - k
        if j >= k:
            wh = hi[j - k : j + k + 1]; wl = lo[j - k : j + k + 1]
            if hi[j] == wh.max() and (wh == hi[j]).sum() == 1:
                last_sh = hi[j]
            if lo[j] == wl.min() and (wl == lo[j]).sum() == 1:
                last_sl = lo[j]
        new = trend
        if last_sh == last_sh and c[i] > last_sh:
            new, last_sh = 1, float("nan")
        elif last_sl == last_sl and c[i] < last_sl:
            new, last_sl = -1, float("nan")
        if new != trend:
            trend = new
            changes.append((idx[i] + delta, trend))
    return changes


def build_htf_context(df_ltf: pd.DataFrame):
    """Зоны со всех HTF + пулы 30m/1h + Order Flow тренды, по времени появления."""
    zones, pools, trends = [], [], {}
    for tf, rule in TF_RULES.items():
        h = resample(df_ltf, rule)
        zones += find_zones(h, tf)
        trends[tf] = trend_series(h, tf)
        if tf in ("30m", "1h"):  # тейки — по пулам 30m-1H (из чек-листа)
            pools += find_pools(h, tf)
    zones.sort(key=lambda z: z.available_from)
    pools.sort(key=lambda p: p.available_from)
    return zones, pools, trends
