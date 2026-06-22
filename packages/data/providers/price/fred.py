"""FRED fiyat sağlayıcı — makro seriler (US10Y/US02Y/CPI).

`FRED_API_KEY` environment değişkeni gerekir. Anahtar yoksa orchestrator
provider'ı 'disabled' işaretler; hata durumunda None → DATA_UNAVAILABLE
(MOCK YOK, fallback YOK).

Makro seriler günlük/aylık güncellenir → modül-seviyesi TTL cache ile
(`FRED_TTL_SEC`, varsayılan 3600sn) boşa ağ çağrısı yapılmaz. Cache yalnızca
GERÇEK son değeri tutar; None cache'lenmez.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from packages.data.types import PriceQuote, utcnow

API = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_SEC = 4.0

# Bizim sembol ↔ FRED series_id
_SYMBOL_MAP = {
    "US10Y": "DGS10",
    "US02Y": "DGS2",
    "CPI":   "CPIAUCSL",
}

SUPPORTED = frozenset(_SYMBOL_MAP.keys())

_DEFAULT_TTL_SEC = 3600
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, PriceQuote]] = {}


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("FRED_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_TTL_SEC)


def _fetch(symbol: str, series_id: str, api_key: str) -> PriceQuote | None:
    url = (
        f"{API}?series_id={series_id}&api_key={api_key}"
        f"&file_type=json&limit=1&sort_order=desc"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    obs = (data.get("observations") or [{}])[0]
    raw = obs.get("value")
    if raw in (None, "", "."):
        return None
    try:
        px = float(raw)
    except (TypeError, ValueError):
        return None
    return PriceQuote(
        symbol=symbol,
        price=px,
        ts=utcnow(),
        source="fred",
        verified=True,
        status="OK",
        fallback=False,
    )


def get_quote(symbol: str) -> PriceQuote | None:
    series_id = _SYMBOL_MAP.get(symbol)
    if series_id is None:
        return None
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(symbol)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    quote = _fetch(symbol, series_id, api_key)
    if quote is not None:
        with _LOCK:
            _CACHE[symbol] = (now, quote)
    return quote
