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
from datetime import UTC, datetime

from packages.data.types import OHLCVBar, PriceQuote, utcnow

API = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_SEC = 4.0
HISTORY_TIMEOUT_SEC = 8.0  # tam seri daha büyük — biraz daha geniş pencere

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
# Geçmiş seri cache'i ayrı (get_history) — anahtar (symbol, start).
_HISTORY_CACHE: dict[tuple[str, str], tuple[float, list[OHLCVBar]]] = {}


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


def _fetch_history(
    symbol: str, series_id: str, api_key: str, start: str | None
) -> list[OHLCVBar]:
    """Tam gözlem serisini (ascending) çeker → 1d OHLCVBar listesi.

    Rate/endeks serisi tek günlük değerdir → o=h=l=c=value (flat bar; uydurma
    OHLC türetmiyoruz, günün TEK gerçek değeri taşınır). '.'/boş gözlem atlanır
    (DATA_POLICY: yalnız gerçek değer). Ağ/parse hatası → [] (fallback YOK)."""
    q = f"{API}?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=asc"
    if start:
        q += f"&observation_start={start}"
    req = urllib.request.Request(q, headers={"User-Agent": "clean-e-yay/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=HISTORY_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    bars: list[OHLCVBar] = []
    for obs in data.get("observations") or []:
        raw = obs.get("value")
        if raw in (None, "", "."):
            continue
        try:
            px = float(raw)
            ts = datetime.strptime(str(obs.get("date")), "%Y-%m-%d").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            continue
        bars.append(
            OHLCVBar(
                symbol=symbol, timeframe="1d", ts=ts,
                open=px, high=px, low=px, close=px, volume=None,
                source="fred", verified=True,
            )
        )
    return bars


def get_history(symbol: str, start: str | None = None) -> list[OHLCVBar]:
    """US10Y/US02Y/CPI için 1d geçmiş seri (ascending). `start`='YYYY-MM-DD'.

    `FRED_API_KEY` yoksa [] (MOCK/fallback YOK — çağıran onu 'veri yok' sayar,
    Likidite katmanı düşer; uydurma OLMAZ). Modül-seviye TTL cache ile aynı
    koşuda tekrar ağ çağrısı yapılmaz."""
    series_id = _SYMBOL_MAP.get(symbol)
    if series_id is None:
        return []
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return []
    key = (symbol, start or "")
    ttl = _ttl_sec()
    now = time.monotonic()
    with _LOCK:
        cached = _HISTORY_CACHE.get(key)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    bars = _fetch_history(symbol, series_id, api_key, start)
    if bars:  # boş sonucu cache'leme (None/[] cache'lenmez — quote deseniyle aynı)
        with _LOCK:
            _HISTORY_CACHE[key] = (now, bars)
    return bars
