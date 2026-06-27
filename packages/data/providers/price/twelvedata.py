"""Twelve Data fiyat sağlayıcı — kripto/emtia fallback.

`TWELVEDATA_API_KEY` yoksa None döner (orchestrator 'disabled' işaretler).
Hata durumunda None → DATA_UNAVAILABLE (MOCK YOK).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from packages.data.types import PriceQuote, utcnow

API = "https://api.twelvedata.com/price"
TIMEOUT_SEC = 4.0

# Bizim sembol ↔ Twelve Data sembolü
_SYMBOL_MAP = {
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

_DEFAULT_TTL_SEC = 60
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("TWELVEDATA_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _fetch(symbol: str, td_symbol: str, api_key: str) -> PriceQuote | None:
    qs = urllib.parse.urlencode({"symbol": td_symbol, "apikey": api_key})
    req = urllib.request.Request(
        f"{API}?{qs}", headers={"User-Agent": "clean-e-yay/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    raw = data.get("price")
    if raw is None:
        return None
    try:
        px = float(raw)
    except (TypeError, ValueError):
        return None
    return PriceQuote(
        symbol=symbol,
        price=px,
        ts=utcnow(),
        source="twelvedata",
        verified=True,
        status="OK",
        fallback=True,
    )


def get_quote(symbol: str) -> PriceQuote | None:
    td_symbol = _SYMBOL_MAP.get(symbol)
    if td_symbol is None:
        return None
    api_key = os.environ.get("TWELVEDATA_API_KEY")
    if not api_key:
        return None
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    quote = _fetch(symbol, td_symbol, api_key)
    if quote is not None:
        with _LOCK:
            _CACHE[symbol] = (now, quote)
    return quote
