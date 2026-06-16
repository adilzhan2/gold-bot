"""OANDA practice фид: настоящий спот XAU_USD, надёжный REST API.

Токен берём из data/oanda.json (или env OANDA_TOKEN). Аккаунт-id для
свечей не нужен — эндпоинт инструментов требует только Bearer-токен.

Свечи: GET /v3/instruments/XAU_USD/candles?granularity=M1&count=5000&price=M
"""
import json
import os
from pathlib import Path

import pandas as pd
import requests

CONFIG = Path(__file__).resolve().parents[2] / "data" / "oanda.json"
BASE = "https://api-fxpractice.oanda.com"  # practice (демо); live — api-fxtrade
INSTRUMENT = "XAU_USD"
MAX_COUNT = 5000  # лимит OANDA на один запрос


def load_token() -> str | None:
    tok = os.environ.get("OANDA_TOKEN")
    if tok:
        return tok
    if CONFIG.exists():
        return json.loads(CONFIG.read_text()).get("token")
    return None


def save_token(token: str):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"token": token}, indent=2))


def is_configured() -> bool:
    return load_token() is not None


def fetch_oanda(granularity: str = "M1", count: int = MAX_COUNT) -> pd.DataFrame:
    """Свечи в формате пайплайна: open/high/low/close/volume, UTC-индекс."""
    token = load_token()
    if not token:
        raise RuntimeError("Нет OANDA-токена (data/oanda.json)")
    r = requests.get(
        f"{BASE}/v3/instruments/{INSTRUMENT}/candles",
        headers={"Authorization": f"Bearer {token}"},
        params={"granularity": granularity, "count": min(count, MAX_COUNT), "price": "M"},
        timeout=20,
    )
    r.raise_for_status()
    candles = r.json().get("candles", [])
    rows = [
        {
            "time": c["time"],
            "open": float(c["mid"]["o"]),
            "high": float(c["mid"]["h"]),
            "low": float(c["mid"]["l"]),
            "close": float(c["mid"]["c"]),
            "volume": c.get("volume", 0),
        }
        for c in candles
        if c.get("complete")  # незакрытую свечу не берём
    ]
    if not rows:
        raise RuntimeError("OANDA вернул пусто")
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.attrs["ticker"] = "XAU_USD (OANDA)"
    return df
