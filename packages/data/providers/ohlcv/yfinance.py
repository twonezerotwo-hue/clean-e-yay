"""Yahoo Finance chart OHLCV adapter — emtia/endeks/volatilite.

Doğrudan Yahoo chart endpoint'i (stdlib HTTP), yfinance paketi gerekmez.
Hata durumunda None döner; orchestrator cache'e döner, mock üretmez.

Native TF'ler: 15m / 1h / 1d / 1wk. 4h, orchestrator'da 1h'ten resample
edilir. Range'ler EMA(200) için yeterli bar verecek şekilde seçildi.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

from packages.data.types import OHLCVBar, Timeframe

API = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEOUT_SEC = 6.0

_SYMBOL_MAP = {
    "XAUUSD": "GC=F",       # Gold futures
    "XAGUSD": "SI=F",       # Silver futures
    "BRENT":  "BZ=F",       # Brent crude
    "DXY":    "DX-Y.NYB",   # Dollar index
    "VIX":    "^VIX",
    "SP500":  "^GSPC",
    "QQQ":    "QQQ",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

# TF → (yahoo interval, range)
_TF_PLAN: dict[str, tuple[str, str]] = {
    "15m": ("15m", "1mo"),
    "1h": ("1h", "1y"),
    "1d": ("1d", "2y"),
    "1w": ("1wk", "5y"),
}

NATIVE_TFS = frozenset(_TF_PLAN.keys())


def get_bars(symbol: str, timeframe: Timeframe) -> list[OHLCVBar] | None:
    ticker = _SYMBOL_MAP.get(symbol)
    plan = _TF_PLAN.get(timeframe)
    if ticker is None or plan is None:
        return None
    interval, rng = plan
    url = f"{API}/{ticker}?interval={interval}&range={rng}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 clean-e-yay/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None
    bars: list[OHLCVBar] = []
    for i, ts in enumerate(timestamps):
        try:
            o, h, lo, c = (
                quote["open"][i],
                quote["high"][i],
                quote["low"][i],
                quote["close"][i],
            )
        except (KeyError, IndexError, TypeError):
            continue
        if None in (o, h, lo, c):
            continue
        vol = None
        try:
            v = quote["volume"][i]
            vol = float(v) if v is not None else None
        except (KeyError, IndexError, TypeError):
            vol = None
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                ts=datetime.fromtimestamp(int(ts), tz=UTC),
                open=float(o),
                high=float(h),
                low=float(lo),
                close=float(c),
                volume=vol,
                source="yfinance",
                verified=True,
            )
        )
    return bars or None
