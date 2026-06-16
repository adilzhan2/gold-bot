"""Live-котировки золота через Yahoo Finance (yfinance).

v1: бесплатно и без регистрации, задержка ~1-2 мин — для алертов хватает.
Когда заведём OANDA practice — заменить fetch() на их API, интерфейс тот же.

Ограничение Yahoo: 1m-свечи отдаются максимум за ~7 дней. Этого хватает
для зон 30m/1H; зоны 4H будут только за неделю (меньше, чем в бэктесте).
"""
import time
from pathlib import Path

import pandas as pd

# yfinance импортируется ЛЕНИВО (только в Yahoo-фолбэке): на сервере
# GitHub Actions его нет, а основной фид — Twelve Data (спот).

# У Yahoo нет спота XAUUSD — берём фьючерс GC=F. Несколько тикеров-фолбэков:
# если Yahoo рейт-лимитит один, пробуем другой источник золота.
TICKERS = ["GC=F", "MGC=F", "GLD"]
_RETRIES = 3       # попыток на тикер при пустом ответе (рейт-лимит Yahoo)
_BACKOFF = 4       # секунд между попытками


def _yf():
    """Ленивая загрузка yfinance + настройка кэша (вызывается только в фолбэке)."""
    import yfinance as yf
    cache = Path(__file__).resolve().parents[2] / "data" / ".yf_cache"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        yf.set_tz_cache_location(str(cache))
    except Exception:  # noqa: BLE001 — старые версии yfinance без этого API
        pass
    return yf


def _try_one(ticker: str, period: str, interval: str) -> pd.DataFrame | None:
    df = _yf().download(ticker, period=period, interval=interval,
                        progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.attrs["ticker"] = ticker
    return df


def fetch(period: str = "5d", interval: str = "1m") -> pd.DataFrame:
    """Свечи в формате пайплайна: open/high/low/close/volume, UTC-индекс.

    Приоритет: Twelve Data → OANDA (оба — спот XAU/USD), если настроены.
    Иначе фолбэк на Yahoo (фьючерс GC=F) с ретраями против рейт-лимита.
    """
    from goldbot.live import oanda, twelvedata

    if twelvedata.is_configured():
        return twelvedata.fetch_td_deep()  # спот + глубокая история (больше зон/сетапов)
    if oanda.is_configured():
        return oanda.fetch_oanda()  # спот, надёжно

    last_err = None
    for ticker in TICKERS:
        for attempt in range(_RETRIES):
            try:
                df = _try_one(ticker, period, interval)
                if df is not None:
                    return df
            except Exception as e:  # noqa: BLE001 — следующая попытка/тикер
                last_err = e
            time.sleep(_BACKOFF)
    raise RuntimeError(f"Не удалось получить котировки (Yahoo рейт-лимит?): {last_err}")
