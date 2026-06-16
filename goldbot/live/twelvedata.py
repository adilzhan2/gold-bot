"""Twelve Data фид: бесплатный ключ, реальный спот XAU/USD, доступен из KZ.

Ключ из data/twelvedata.json (или env TWELVEDATA_KEY).
Лимит free: 8 запросов/мин, 800/день — при опросе раз в 3 мин (480/день) ок.

Свечи: GET https://api.twelvedata.com/time_series
       ?symbol=XAU/USD&interval=1min&outputsize=5000&timezone=UTC&apikey=...
"""
import json
import os
from pathlib import Path

import pandas as pd
import requests

CONFIG = Path(__file__).resolve().parents[2] / "data" / "twelvedata.json"
SYMBOL = "XAU/USD"
MAX_OUTPUT = 5000  # потолок free-тарифа


def load_key() -> str | None:
    key = os.environ.get("TWELVEDATA_KEY")
    if key:
        return key
    if CONFIG.exists():
        return json.loads(CONFIG.read_text()).get("key")
    return None


def save_key(key: str):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"key": key}, indent=2))


def is_configured() -> bool:
    return load_key() is not None


def fetch_td(interval: str = "1min", outputsize: int = MAX_OUTPUT) -> pd.DataFrame:
    """Свечи в формате пайплайна: open/high/low/close/volume, UTC-индекс."""
    key = load_key()
    if not key:
        raise RuntimeError("Нет ключа Twelve Data (data/twelvedata.json)")
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": SYMBOL,
            "interval": interval,
            "outputsize": min(outputsize, MAX_OUTPUT),
            "timezone": "UTC",
            "apikey": key,
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok" or "values" not in data:
        raise RuntimeError(f"Twelve Data ошибка: {data.get('message', data)}")

    df = pd.DataFrame(data["values"])
    df["time"] = pd.to_datetime(df["datetime"], utc=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    df["volume"] = df.get("volume", 0)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = (
        df.set_index("time")[["open", "high", "low", "close", "volume"]]
        .sort_index()  # Twelve Data отдаёт от новых к старым — разворачиваем
    )
    df = df[~df.index.duplicated(keep="last")]
    df.attrs["ticker"] = "XAU/USD (TwelveData)"
    return df
