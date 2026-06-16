"""Рендер сетапа в PNG: свечи ДО момента входа (без будущего!),
зона интереса, sweep, линии entry/SL/TP.

Будущее на картинке = читерская разметка: ты бы оценивал сетап,
уже зная исход. Поэтому график обрезается баром подтверждения.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import mplfinance as mpf
import pandas as pd

LOOKBACK = 180  # баров на картинке


def render_setup(
    df: pd.DataFrame,
    bar: int,
    direction: int,
    entry: float,
    sl: float,
    tp: float,
    zone_top: float,
    zone_bottom: float,
    sweep_bar: int,
    out_path: Path,
    title: str = "",
):
    start = max(0, bar - LOOKBACK)
    win = df.iloc[start : bar + 1]

    kwargs = dict(
        type="candle",
        style="nightclouds",
        figsize=(12, 7),
        hlines=dict(
            hlines=[entry, sl, tp],
            colors=["#e0e0e0", "#ff5555", "#50fa7b"],
            linestyle="--",
            linewidths=1,
        ),
        title=title,
        ylabel="",
        savefig=dict(fname=str(out_path), dpi=90, bbox_inches="tight"),
    )
    # зона интереса HTF — полупрозрачная полоса
    if zone_top == zone_top and zone_bottom == zone_bottom:  # not NaN
        kwargs["fill_between"] = dict(y1=zone_bottom, y2=zone_top, alpha=0.15, color="#8be9fd")
    # момент свипа — вертикальный пунктир
    if 0 <= sweep_bar < len(df) and sweep_bar >= start:
        kwargs["vlines"] = dict(
            vlines=[df.index[sweep_bar]], colors=["#ffb86c"], linestyle=":", linewidths=1
        )

    mpf.plot(win, **kwargs)
