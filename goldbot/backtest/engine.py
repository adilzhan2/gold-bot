"""Бэктест на out-of-sample: берём сетапы, фильтруем по скору модели,
складываем R-результаты (они уже учитывают спред — см. labeling).

Это упрощённый бэктест "по сделкам", без переcечения позиций.
Достаточно, чтобы понять, есть ли edge. Точную симуляцию — потом.
"""
import numpy as np
import pandas as pd


def run_backtest(test_df: pd.DataFrame, scores: np.ndarray, threshold: float = 0.5) -> dict:
    ds = test_df.copy()
    ds["score"] = scores
    taken = ds[ds["score"] >= threshold].sort_values("time")
    baseline = ds  # "брать все сетапы без модели" — наш бенчмарк

    def stats(trades: pd.DataFrame, name: str) -> dict:
        if trades.empty:
            return {"name": name, "trades": 0}
        r = trades["r"].values
        equity = np.cumsum(r)
        dd = (np.maximum.accumulate(equity) - equity).max()
        return {
            "name": name,
            "trades": len(r),
            "winrate": float((r > 0).mean()),
            "total_R": float(r.sum()),
            "avg_R": float(r.mean()),
            "max_drawdown_R": float(dd),
        }

    result = {
        "model": stats(taken, f"model@{threshold}"),
        "baseline": stats(baseline, "все сетапы"),
    }
    for s in result.values():
        if s["trades"]:
            print(
                f"{s['name']:>14}: {s['trades']:5d} сделок | winrate {s['winrate']:.1%} | "
                f"total {s['total_R']:+.1f}R | avg {s['avg_R']:+.3f}R | maxDD {s['max_drawdown_R']:.1f}R"
            )
        else:
            print(f"{s['name']:>14}: 0 сделок")
    return result
