"""SMC-структура рынка: swing points, BOS/CHoCH, FVG, liquidity sweeps.

ГЛАВНОЕ ПРАВИЛО — никакого lookahead:
фича на баре i может использовать только данные баров <= i.
Swing high подтверждается лишь через K баров после экстремума —
поэтому "знание" о нём появляется с задержкой K. Это честно
воспроизводит то, что ты видишь на живом графике.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SWING_K = 3  # баров слева/справа для подтверждения свинга


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — наша "линейка" для нормализации расстояний."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


@dataclass
class _Structure:
    """Состояние рыночной структуры на текущий момент (state machine)."""

    trend: int = 0  # +1 бычий, -1 медвежий, 0 неизвестно
    last_swing_high: float = np.nan
    last_swing_low: float = np.nan
    bars_since_bos: int = 9999
    # бычьи FVG (зоны поддержки): список (низ, верх); медвежьи симметрично
    bull_fvgs: list = field(default_factory=list)
    bear_fvgs: list = field(default_factory=list)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Проходит по свечам и считает SMC-фичи для каждого бара.

    Возвращает DataFrame с фичами + колонками-флагами кандидатов
    (long_setup / short_setup): бар, где по структуре есть сетап.
    """
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    atr_ = atr(df).values

    s = _Structure()
    out = {
        "trend": np.zeros(n),
        "bars_since_bos": np.full(n, 9999.0),
        "dist_to_swing_high_atr": np.full(n, np.nan),
        "dist_to_swing_low_atr": np.full(n, np.nan),
        "in_bull_fvg": np.zeros(n),
        "in_bear_fvg": np.zeros(n),
        "swept_low": np.zeros(n),   # liquidity sweep вниз (снос стопов под лоем)
        "swept_high": np.zeros(n),
        "long_setup": np.zeros(n, bool),
        "short_setup": np.zeros(n, bool),
    }

    for i in range(n):
        # --- 1. Подтверждение свингов: на баре i подтверждается экстремум
        # бара j = i - SWING_K (мы только сейчас увидели K баров справа от него)
        j = i - SWING_K
        if j >= SWING_K:
            win_h = high[j - SWING_K : j + SWING_K + 1]
            win_l = low[j - SWING_K : j + SWING_K + 1]
            if high[j] == win_h.max() and (win_h == high[j]).sum() == 1:
                # sweep: прокололи прошлый хай и закрылись ниже него
                if not np.isnan(s.last_swing_high) and high[j] > s.last_swing_high and close[j] < s.last_swing_high:
                    out["swept_high"][i] = 1
                s.last_swing_high = high[j]
            if low[j] == win_l.min() and (win_l == low[j]).sum() == 1:
                if not np.isnan(s.last_swing_low) and low[j] < s.last_swing_low and close[j] > s.last_swing_low:
                    out["swept_low"][i] = 1
                s.last_swing_low = low[j]

        # --- 2. BOS / CHoCH: закрытие за подтверждённый свинг
        if not np.isnan(s.last_swing_high) and close[i] > s.last_swing_high:
            s.trend = 1  # бычий BOS (или CHoCH, если тренд был -1)
            s.bars_since_bos = 0
            s.last_swing_high = np.nan  # уровень пробит, ждём новый свинг
        elif not np.isnan(s.last_swing_low) and close[i] < s.last_swing_low:
            s.trend = -1
            s.bars_since_bos = 0
            s.last_swing_low = np.nan
        else:
            s.bars_since_bos += 1

        # --- 3. FVG: бычий гэп = low[i] > high[i-2] (известен на закрытии i)
        if i >= 2:
            if low[i] > high[i - 2]:
                s.bull_fvgs.append((high[i - 2], low[i]))
            if high[i] < low[i - 2]:
                s.bear_fvgs.append((high[i], low[i - 2]))
        # FVG считаем "отработанным" после полного перекрытия ценой
        s.bull_fvgs = [(lo, hi) for lo, hi in s.bull_fvgs if low[i] > lo][-10:]
        s.bear_fvgs = [(lo, hi) for lo, hi in s.bear_fvgs if high[i] < hi][-10:]

        in_bull = any(lo <= low[i] <= hi for lo, hi in s.bull_fvgs)
        in_bear = any(lo <= high[i] <= hi for lo, hi in s.bear_fvgs)

        # --- 4. Фичи бара
        out["trend"][i] = s.trend
        out["bars_since_bos"][i] = min(s.bars_since_bos, 500)
        a = atr_[i] if atr_[i] and not np.isnan(atr_[i]) else np.nan
        if not np.isnan(s.last_swing_high) and a:
            out["dist_to_swing_high_atr"][i] = (s.last_swing_high - close[i]) / a
        if not np.isnan(s.last_swing_low) and a:
            out["dist_to_swing_low_atr"][i] = (close[i] - s.last_swing_low) / a
        out["in_bull_fvg"][i] = in_bull
        out["in_bear_fvg"][i] = in_bear

        # --- 5. Кандидаты-сетапы (TODO: подгони под СВОЮ тактику!)
        # Базовый шаблон: тренд + возврат цены в FVG по тренду = вход
        if s.trend == 1 and in_bull and s.bars_since_bos < 100:
            out["long_setup"][i] = True
        if s.trend == -1 and in_bear and s.bars_since_bos < 100:
            out["short_setup"][i] = True

    feat = pd.DataFrame(out, index=df.index)
    feat["atr"] = atr_

    # --- 6. Время: сессии решают в золоте (Лондон/НЙ — основное движение)
    hours = df.index.hour
    feat["session_asia"] = ((hours >= 0) & (hours < 7)).astype(float)
    feat["session_london"] = ((hours >= 7) & (hours < 13)).astype(float)
    feat["session_ny"] = ((hours >= 13) & (hours < 21)).astype(float)
    feat["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    return feat


FEATURE_COLS = [
    "trend",
    "bars_since_bos",
    "dist_to_swing_high_atr",
    "dist_to_swing_low_atr",
    "in_bull_fvg",
    "in_bear_fvg",
    "swept_low",
    "swept_high",
    "atr",
    "session_asia",
    "session_london",
    "session_ny",
    "hour_sin",
    "hour_cos",
]
