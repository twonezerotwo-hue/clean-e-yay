"""SEC EDGAR — şirket fundamentals (key gerektirmez, User-Agent zorunlu).

SEC, tüm `data.sec.gov` çağrılarında tanımlayıcı bir User-Agent ister
(rate-limit/kötüye kullanım takibi için) — API key değildir.

Henüz karar zincirine/dashboard'a bağlanmadı — bu modül sadece fetch
katmanını sağlar (DATA_POLICY: hata → None, mock yok).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

USER_AGENT = "clean-e-yay research contact:twonezerotwo@gmail.com"
API_TICKERS = "https://www.sec.gov/files/company_tickers.json"
API_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
TIMEOUT_SEC = 6.0

_DEFAULT_TTL_SEC = 86400  # fundamentals nadiren değişir
_LOCK = threading.Lock()
_TICKER_MAP_CACHE: tuple[float, dict[str, int]] | None = None
_FACTS_CACHE: dict[int, tuple[float, dict]] = {}


def _get_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _ticker_map() -> dict[str, int]:
    """Ticker → CIK eşlemesi (tek seferde indirilir, günde 1 yenilenir)."""
    global _TICKER_MAP_CACHE
    now = time.monotonic()
    with _LOCK:
        if _TICKER_MAP_CACHE and (now - _TICKER_MAP_CACHE[0]) < _DEFAULT_TTL_SEC:
            return _TICKER_MAP_CACHE[1]
    data = _get_json(API_TICKERS)
    if not isinstance(data, dict):
        return {}
    mapping = {
        str(row.get("ticker", "")).upper(): int(row.get("cik_str", 0))
        for row in (data.values() if isinstance(data, dict) else [])
        if isinstance(row, dict) and row.get("ticker")
    }
    with _LOCK:
        _TICKER_MAP_CACHE = (now, mapping)
    return mapping


def cik_for_ticker(ticker: str) -> int | None:
    return _ticker_map().get(ticker.upper())


def get_company_facts(ticker: str) -> dict | None:
    """Şirketin XBRL fundamentals verisi (ham SEC JSON). Hata → None."""
    cik = cik_for_ticker(ticker)
    if cik is None:
        return None
    now = time.monotonic()
    with _LOCK:
        cached = _FACTS_CACHE.get(cik)
        if cached and (now - cached[0]) < _DEFAULT_TTL_SEC:
            return cached[1]
    data = _get_json(API_FACTS.format(cik=cik))
    if data is None:
        return None
    with _LOCK:
        _FACTS_CACHE[cik] = (now, data)
    return data
