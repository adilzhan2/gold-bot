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


def fetch_td(interval: str = "1min", outputsize: int = MAX_OUTPUT, symbol: str = SYMBOL) -> pd.DataFrame:
    """Свечи в формате пайплайна (один запрос, до 5000 баров). symbol — любой инструмент."""
    key = load_key()
    if not key:
        raise RuntimeError("Нет ключа Twelve Data (data/twelvedata.json)")
    df = _one_request(key, interval, min(outputsize, MAX_OUTPUT), symbol=symbol)
    df.attrs["ticker"] = f"{symbol} (TwelveData)"
    return df


def _one_request(key: str, interval: str, outputsize: int, end_date: str | None = None,
                 symbol: str = SYMBOL) -> pd.DataFrame:
    params = {
        "symbol": symbol, "interval": interval, "outputsize": outputsize,
        "timezone": "UTC", "apikey": key,
    }
    if end_date:
        params["end_date"] = end_date  # тянем окно ДО этой даты (для пагинации вглубь)
    r = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok" or "values" not in data:
        raise RuntimeError(f"Twelve Data ошибка: {data.get('message', data)}")

    df = pd.DataFrame(data["values"])
    df["time"] = pd.to_datetime(df["datetime"], utc=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    else:
        df["volume"] = 0.0  # у форекса XAU/USD объёма нет
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]].sort_index()
    return df[~df.index.duplicated(keep="last")]


def fetch_td_deep(bars: int = 12000, interval: str = "1min") -> pd.DataFrame:
    """Глубокая история постранично (нужна для 4H-зон → больше сетапов).

    Каждый запрос ≤5000 баров; идём вглубь по end_date. 12000 баров 1m ≈
    2-3 недели торговли = 3 запроса. На free 800/день при опросе раз в 15 мин
    (96×3=288/день) укладываемся с запасом.
    """
    key = load_key()
    if not key:
        raise RuntimeError("Нет ключа Twelve Data (data/twelvedata.json)")

    parts: list[pd.DataFrame] = []
    have = 0
    end = None
    while have < bars:
        chunk = _one_request(key, interval, MAX_OUTPUT, end_date=end)
        if chunk.empty:
            break
        parts.append(chunk)
        have += len(chunk)
        # следующее окно — строго ДО самой старой свечи текущего
        oldest = chunk.index[0]
        end = (oldest - pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        if len(chunk) < MAX_OUTPUT:  # история кончилась
            break

    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.attrs["ticker"] = "XAU/USD (TwelveData)"
    return df
