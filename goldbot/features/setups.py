"""Генератор сетапов по чек-листу (XAUUSD, SMC):

1. Order Flow — направление по структуре HTF (4H/1H/30m)
2. TOUCH — цена зашла в HTF-зону (OB+имбаланс на 30m/1H/4H)
3. SWEEP — на LTF фитиль снял локальный экстремум, тело закрылось обратно
4. CHoCH — импульс ТЕЛОМ сломал ближайший LTF-свинг
5. импульс оставил LTF-имбаланс (FVG)
→ лимитка на край имбаланса, стоп за фитиль sweep + буфер,
  тейк — ближайший пул ликвидности (равные хаи/лои 30m-1H).

Работает на m1 или m5 — окна заданы в минутах и пересчитываются в бары.
Выравнивание по Order Flow — фича (модель учится), не жёсткий фильтр:
жёсткий фильтр можно включить на бэктесте.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from goldbot.features.htf import build_htf_context
from goldbot.features.smc import atr

# --- параметры тактики (крутить тут; окна — в МИНУТАХ) ---
TOUCH_WINDOW_MIN = 360   # 6ч на появление sweep после касания зоны
CHOCH_WINDOW_MIN = 150   # 2.5ч от sweep до CHoCH
ATR_WINDOW_MIN = 70      # ATR на ~70 минутах (14 баров m5)
LTF_SWING_K = 2          # свинги LTF в барах
WICK_MIN_ATR = 0.05      # минимальная длина фитиля sweep (в ATR)
SPREAD = 0.35            # $ на XAUUSD
SL_BUFFER_ATR = 0.15     # техотступ за фитилём (+ спред добавляется отдельно)
MIN_RR = 1.2             # если до пула меньше — сетап пропускаем
MAX_RR = 8.0             # дальше пул нереалистичен → режем цель до MAX_RR (без «лунных» RR 100)
FALLBACK_RR = 2.5        # запасная фикс-цель, если пула ликвидности нет (0 = строгий режим)
MIN_RISK_USD = 1.0       # микро-стопы < 1$ — шум, спред съедает всё
MAX_TOUCHES = 2          # сколько касаний зоны отрабатываем
MAX_ACTIVE_ZONES = 40
EQ_LOOKBACK_MIN = 720    # окно поиска равных хаёв/лоёв перед свипом (12ч)
EQ_TOL_ATR = 0.10        # насколько близко к свипу = "равный" уровень
RANGE_WINDOW_MIN = 1440  # окно для оценки достижимости цели (1 день)


@dataclass
class Setup:
    bar: int                  # бар подтверждения (CHoCH) — лимитку ставим после него
    time: pd.Timestamp
    direction: int            # +1 long, -1 short
    entry: float              # край LTF-имбаланса
    sl: float                 # за фитиль sweep + буфер + спред
    tp: float                 # пул ликвидности
    features: dict
    # для отрисовки графика сетапа
    zone_top: float = float("nan")
    zone_bottom: float = float("nan")
    sweep_bar: int = -1
    sweep_px: float = float("nan")


def bar_minutes(df: pd.DataFrame) -> int:
    """Шаг данных в минутах (1 для m1, 5 для m5)."""
    return int(df.index.to_series().diff().dropna().mode()[0].total_seconds() // 60)


def _ltf_fvg_in(hi, lo, a, b, direction):
    """Ищет FVG внутри импульса [a..b]; возвращает (край входа, размер) или None."""
    for i in range(max(a, 2), b + 1):
        if direction == 1 and lo[i] > hi[i - 2]:
            return lo[i], lo[i] - hi[i - 2]   # вход на верхний край бычьего гэпа
        if direction == -1 and hi[i] < lo[i - 2]:
            return hi[i], lo[i - 2] - hi[i]
    return None


def generate_setups(df: pd.DataFrame) -> list[Setup]:
    o = df["open"].values
    hi = df["high"].values
    lo = df["low"].values
    c = df["close"].values
    idx = df.index
    n = len(df)

    bm = bar_minutes(df)
    touch_w = TOUCH_WINDOW_MIN // bm
    choch_w = CHOCH_WINDOW_MIN // bm
    atr_ = atr(df, period=max(ATR_WINDOW_MIN // bm, 5)).values

    zones, pools, trends = build_htf_context(df)
    zi = pi = 0
    ti = {tf: 0 for tf in trends}
    cur_trend = {tf: 0 for tf in trends}
    active_zones: list = []
    active_pools: list = []
    touches: dict = {}  # id(zone) -> счётчик касаний

    # LTF-свинги (подтверждаются с лагом K)
    last_sh = last_sl = np.nan
    k = LTF_SWING_K

    # состояние: None | dict(stage='touched'|'swept', ...)
    state = None
    setups: list[Setup] = []
    hours = idx.hour
    days = idx.dayofyear

    # пулы "по умолчанию": хай/лоу предыдущего дня (PDH/PDL) — классика
    cur_day_hi = cur_day_lo = np.nan
    pdh = pdl = np.nan  # NaN = нет / снят

    for i in range(n):
        t = idx[i]
        # --- PDH/PDL: на смене дня вчерашние экстремумы становятся целями ---
        if i > 0 and days[i] != days[i - 1]:
            pdh, pdl = cur_day_hi, cur_day_lo
            cur_day_hi = cur_day_lo = np.nan
        cur_day_hi = hi[i] if np.isnan(cur_day_hi) else max(cur_day_hi, hi[i])
        cur_day_lo = lo[i] if np.isnan(cur_day_lo) else min(cur_day_lo, lo[i])
        if not np.isnan(pdh) and hi[i] > pdh:
            pdh = np.nan  # снят
        if not np.isnan(pdl) and lo[i] < pdl:
            pdl = np.nan
        # --- подкидываем появившиеся зоны/пулы/смены тренда ---
        while zi < len(zones) and zones[zi].available_from <= t:
            active_zones.append(zones[zi]); zi += 1
        while pi < len(pools) and pools[pi].available_from <= t:
            active_pools.append(pools[pi]); pi += 1
        for tf, ch in trends.items():
            while ti[tf] < len(ch) and ch[ti[tf]][0] <= t:
                cur_trend[tf] = ch[ti[tf]][1]; ti[tf] += 1
        if len(active_zones) > MAX_ACTIVE_ZONES:
            active_zones = active_zones[-MAX_ACTIVE_ZONES:]
        # инвалидация: закрытие за зоной / снятый пул
        active_zones = [z for z in active_zones
                        if not (z.kind == 1 and c[i] < z.bottom) and not (z.kind == -1 and c[i] > z.top)]
        active_pools = [p for p in active_pools
                        if not (p.kind == 1 and hi[i] > p.level) and not (p.kind == -1 and lo[i] < p.level)]

        # --- LTF-свинги ---
        j = i - k
        if j >= k:
            wh = hi[j - k : j + k + 1]; wl = lo[j - k : j + k + 1]
            if hi[j] == wh.max() and (wh == hi[j]).sum() == 1:
                last_sh = hi[j]
            if lo[j] == wl.min() and (wl == lo[j]).sum() == 1:
                last_sl = lo[j]

        a = atr_[i]
        if np.isnan(a) or a <= 0:
            continue

        # --- 2. TOUCH: бар пересёк активную зону ---
        if state is None:
            for z in active_zones:
                if lo[i] <= z.top and hi[i] >= z.bottom:
                    depth = ((z.top - lo[i]) / (z.top - z.bottom + 1e-9) if z.kind == 1
                             else (hi[i] - z.bottom) / (z.top - z.bottom + 1e-9))
                    cnt = touches.get(id(z), 0) + 1
                    touches[id(z)] = cnt
                    state = {"stage": "touched", "zone": z, "since": i,
                             "depth": min(depth, 1.0), "touch_n": cnt}
                    if cnt >= MAX_TOUCHES:
                        active_zones.remove(z)
                    break
            continue

        d = state["zone"].kind  # направление сделки задаёт зона
        if i - state["since"] > touch_w + (choch_w if state["stage"] == "swept" else 0):
            state = None
            continue

        # --- 3. SWEEP: фитиль снял свинг, тело вернулось ---
        if state["stage"] == "touched":
            if d == 1 and not np.isnan(last_sl) and lo[i] < last_sl and c[i] > last_sl \
                    and (min(o[i], c[i]) - lo[i]) >= WICK_MIN_ATR * a:
                state.update(stage="swept", sweep_px=lo[i], sweep_bar=i,
                             wick=(min(o[i], c[i]) - lo[i]) / a, broke=last_sh)
            elif d == -1 and not np.isnan(last_sh) and hi[i] > last_sh and c[i] < last_sh \
                    and (hi[i] - max(o[i], c[i])) >= WICK_MIN_ATR * a:
                state.update(stage="swept", sweep_px=hi[i], sweep_bar=i,
                             wick=(hi[i] - max(o[i], c[i])) / a, broke=last_sl)
            continue

        # --- 4. CHoCH телом + 5. импульс оставил FVG ---
        lvl = state["broke"]  # ближайший свинг против направления на момент sweep
        if np.isnan(lvl):
            state = None
            continue
        choch = (d == 1 and c[i] > lvl) or (d == -1 and c[i] < lvl)
        if not choch:
            continue

        fvg = _ltf_fvg_in(hi, lo, state["sweep_bar"], i, d)
        state_, state = state, None  # сетап либо есть, либо нет — state сбрасываем
        if fvg is None:
            continue
        entry, fvg_size = fvg

        sl = state_["sweep_px"] - d * (SL_BUFFER_ATR * a + SPREAD)
        risk = d * (entry - sl)
        if risk < MIN_RISK_USD:
            continue

        # --- тейк: ближайший пул ликвидности по направлению (equal H/L + PDH/PDL) ---
        if d == 1:
            cands = [p.level for p in active_pools if p.kind == 1 and p.level > entry + MIN_RR * risk]
            if not np.isnan(pdh) and pdh > entry + MIN_RR * risk:
                cands.append(pdh)
            tp = min(cands) if cands else np.nan
        else:
            cands = [p.level for p in active_pools if p.kind == -1 and p.level < entry - MIN_RR * risk]
            if not np.isnan(pdl) and pdl < entry - MIN_RR * risk:
                cands.append(pdl)
            tp = max(cands) if cands else np.nan
        if np.isnan(tp):
            # пула нет — запасная фикс-цель FALLBACK_RR (чтобы сетап не терять)
            if FALLBACK_RR:
                tp = entry + d * FALLBACK_RR * risk
            else:
                continue  # строгий режим: целимся только в ликвидность
        elif d * (tp - entry) / risk > MAX_RR:
            tp = entry + d * MAX_RR * risk  # режем недостижимо далёкий пул

        z = state_["zone"]
        h = hours[i]
        sweep_px = state_["sweep_px"]
        sweep_bar = state_["sweep_bar"]

        # --- #1 chasing: как далеко вход ушёл от экстремума свипа (в ATR) ---
        chase_atr = d * (entry - sweep_px) / a

        # --- #3а сторона POI: бокс на правильной стороне от входа? ---
        box_mid = (z.top + z.bottom) / 2
        poi_aligned = float(d * (entry - box_mid) > 0)

        # --- #3б equal highs/lows: сколько раз цену тянуло к свипу заранее ---
        lb = max(sweep_bar - EQ_LOOKBACK_MIN // bm, 0)
        tol = EQ_TOL_ATR * a
        if d == 1:  # снимали лои → ищем равные лои у sweep_px
            eq_touches = int(np.sum(np.abs(lo[lb:sweep_bar] - sweep_px) <= tol))
        else:
            eq_touches = int(np.sum(np.abs(hi[lb:sweep_bar] - sweep_px) <= tol))

        # --- #4 достижимость цели: путь до тейка / реальный диапазон рынка ---
        rw = max(i - RANGE_WINDOW_MIN // bm, 0)
        rng = hi[rw:i + 1].max() - lo[rw:i + 1].min()
        target_reach = (d * (tp - entry)) / rng if rng > 0 else np.nan

        setups.append(Setup(
            bar=i, time=t, direction=d, entry=entry, sl=sl, tp=tp,
            zone_top=z.top, zone_bottom=z.bottom,
            sweep_bar=sweep_bar, sweep_px=sweep_px,
            features={
                "direction": d,
                # --- Order Flow: тренды HTF и согласованность зоны ---
                "htf_trend_30m": cur_trend["30m"],
                "htf_trend_1h": cur_trend["1h"],
                "htf_trend_4h": cur_trend["4h"],
                "zone_aligned": float(cur_trend[z.tf] == z.kind),
                "zone_tf_30m": float(z.tf == "30m"),
                "zone_tf_1h": float(z.tf == "1h"),
                "zone_tf_4h": float(z.tf == "4h"),
                "zone_height_atr": (z.top - z.bottom) / a,
                "touch_depth": state_["depth"],
                "touch_n": float(state_["touch_n"]),
                "sweep_wick_atr": state_["wick"],
                "sweep_to_choch_bars": (i - sweep_bar) * bm,  # в минутах
                "choch_impulse_atr": d * (c[i] - sweep_px) / a,
                "ltf_fvg_size_atr": fvg_size / a,
                "risk_atr": risk / a,
                "rr_target": d * (tp - entry) / risk,
                "atr": a,
                # --- фичи из разбора трейдов (chase / POI / equal liq / reach) ---
                "chase_atr": chase_atr,
                "poi_aligned": poi_aligned,
                "eq_touches": float(eq_touches),
                "target_reach": target_reach,
                "session_asia": float(0 <= h < 7),
                "session_london": float(7 <= h < 13),
                "session_ny": float(13 <= h < 21),
                "hour_sin": np.sin(2 * np.pi * h / 24),
                "hour_cos": np.cos(2 * np.pi * h / 24),
            },
        ))

    return setups


FEATURE_COLS = [
    "direction",
    "htf_trend_30m", "htf_trend_1h", "htf_trend_4h", "zone_aligned",
    "zone_tf_30m", "zone_tf_1h", "zone_tf_4h",
    "zone_height_atr", "touch_depth", "touch_n",
    "sweep_wick_atr", "sweep_to_choch_bars", "choch_impulse_atr",
    "ltf_fvg_size_atr", "risk_atr", "rr_target", "atr",
    "chase_atr", "poi_aligned", "eq_touches", "target_reach",
    "session_asia", "session_london", "session_ny", "hour_sin", "hour_cos",
]
