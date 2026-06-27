"""Finnhub fiyat sağlayıcı — kripto fallback (Binance üzerinden quote).

`FINNHUB_API_KEY` yoksa None döner (orchestrator 'disabled' işaretler).
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

API = "https://finnhub.io/api/v1/quote"
TIMEOUT_SEC = 4.0

# Bizim sembol ↔ Finnhub sembolü (Binance exchange-prefixed)
_SYMBOL_MAP = {
    "BTCUSD": "BINANCE:BTCUSDT",
    "ETHUSD": "BINANCE:ETHUSDT",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

_DEFAULT_TTL_SEC = 60
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("FINNHUB_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _fetch(symbol: str, fh_symbol: str, api_key: str) -> PriceQuote | None:
    qs = urllib.parse.urlencode({"symbol": fh_symbol, "token": api_key})
    req = urllib.request.Request(
        f"{API}?{qs}", headers={"User-Agent": "clean-e-yay/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    raw = data.get("c")
    if not raw:
        return None
    try:
        px = float(raw)
    except (TypeError, ValueError):
        return None
    return PriceQuote(
        symbol=symbol,
        price=px,
        ts=utcnow(),
        source="finnhub",
        verified=True,
        status="OK",
        fallback=True,
    )


def get_quote(symbol: str) -> PriceQuote | None:
    fh_symbol = _SYMBOL_MAP.get(symbol)
    if fh_symbol is None:
        return None
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return None
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    quote = _fetch(symbol, fh_symbol, api_key)
    if quote is not None:
        with _LOCK:
            _CACHE[symbol] = (now, quote)
    return quote
