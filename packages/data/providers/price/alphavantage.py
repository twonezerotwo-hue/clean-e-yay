"""Alpha Vantage fiyat sağlayıcı — kripto/emtia fallback (CURRENCY_EXCHANGE_RATE).

`ALPHAVANTAGE_API_KEY` yoksa None döner (orchestrator 'disabled' işaretler).
Ücretsiz plan 25 çağrı/gün ile sınırlı → uzun TTL (varsayılan 900sn).
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

API = "https://www.alphavantage.co/query"
TIMEOUT_SEC = 4.0

# Bizim sembol ↔ (from_currency, to_currency)
_SYMBOL_MAP = {
    "BTCUSD": ("BTC", "USD"),
    "ETHUSD": ("ETH", "USD"),
    "XAUUSD": ("XAU", "USD"),
    "XAGUSD": ("XAG", "USD"),
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

_DEFAULT_TTL_SEC = 900
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("ALPHAVANTAGE_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _fetch(symbol: str, from_cur: str, to_cur: str, api_key: str) -> PriceQuote | None:
    qs = urllib.parse.urlencode(
        {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_cur,
            "to_currency": to_cur,
            "apikey": api_key,
        }
    )
    req = urllib.request.Request(
        f"{API}?{qs}", headers={"User-Agent": "clean-e-yay/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    node = data.get("Realtime Currency Exchange Rate") or {}
    raw = node.get("5. Exchange Rate")
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
        source="alphavantage",
        verified=True,
        status="OK",
        fallback=True,
    )


def get_quote(symbol: str) -> PriceQuote | None:
    pair = _SYMBOL_MAP.get(symbol)
    if pair is None:
        return None
    api_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return None
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    quote = _fetch(symbol, pair[0], pair[1], api_key)
    if quote is not None:
        with _LOCK:
            _CACHE[symbol] = (now, quote)
    return quote
