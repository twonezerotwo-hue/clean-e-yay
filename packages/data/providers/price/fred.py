"""FRED fiyat sağlayıcı — makro seriler (US10Y).

`FRED_API_KEY` environment değişkeni gerekir. Anahtar yoksa veya hata
durumunda None döner; orchestrator mock'a düşer.
"""
from __future__ import annotations

import json
import os
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


def get_quote(symbol: str) -> PriceQuote | None:
    series_id = _SYMBOL_MAP.get(symbol)
    if series_id is None:
        return None
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None
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
        fallback=False,
    )
