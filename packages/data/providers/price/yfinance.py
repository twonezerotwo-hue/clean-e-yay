"""Yahoo Finance fiyat sağlayıcı — emtia/endeks/volatilite.

Doğrudan Yahoo chart endpoint'i kullanılır (stdlib HTTP). yfinance paketi
gerektirmez. Hata durumunda None döner.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from packages.data.registry import custom_assets
from packages.data.types import PriceQuote, utcnow

API = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEOUT_SEC = 4.0

# Bizim sembol ↔ Yahoo ticker
_SYMBOL_MAP = {
    "XAUUSD": "GC=F",       # Gold futures
    "XAGUSD": "SI=F",       # Silver futures
    "BRENT":  "BZ=F",       # Brent crude
    "DXY":    "DX-Y.NYB",   # Dollar index
    "VIX":    "^VIX",
    "SP500":  "^GSPC",
    "QQQ":    "QQQ",
}

SUPPORTED = custom_assets.DynamicSymbolSet(frozenset(_SYMBOL_MAP.keys()), "yfinance")


def get_quote(symbol: str) -> PriceQuote | None:
    ticker = _SYMBOL_MAP.get(symbol) or custom_assets.ticker_for(symbol, "yfinance")
    if ticker is None:
        return None
    url = f"{API}/{ticker}?interval=1d&range=1d"
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
        px = result["meta"]["regularMarketPrice"]
    except (KeyError, IndexError, TypeError):
        return None
    if px is None:
        return None
    return PriceQuote(
        symbol=symbol,
        price=float(px),
        ts=utcnow(),
        source="yfinance",
        verified=True,
        status="OK",
        fallback=False,
    )
