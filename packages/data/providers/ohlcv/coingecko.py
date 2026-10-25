"""CoinGecko market_chart OHLCV adapter — kripto (BTC/ETH).

Demo API anahtarı (`COINGECKO_API_KEY`) varsa kimlik doğrulamalı çağrılır
(`x-cg-demo-api-key`). Hata/timeout durumunda None döner; orchestrator
DATA_UNAVAILABLE verir, MOCK üretmez.

Granülarite (CoinGecko market_chart otomatik):
- days=1   → ~5 dakikalık fiyat noktaları → 15m barlara resample edilir
             (`source="resampled:coingecko_5m"`).
- days=90  → saatlik fiyat noktaları → 1h bar (nokta başına tek fiyat;
             o=h=l=c, ATR bu TF'te alt sınır tahminidir).
- days=365 → günlük fiyat noktaları → 1d bar.
- 4h ve 1w bu modülde üretilmez — orchestrator 1h/1d'den resample eder.

Volume: market_chart `total_volumes` 24 saatlik kayan toplamdır, bar
hacmi değildir → volume=None bırakılır (yanlış veri taşımamak için).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from packages.data.providers import coingecko_auth
from packages.data.registry import custom_assets
from packages.data.types import OHLCVBar, Timeframe

API = "https://api.coingecko.com/api/v3/coins"
TIMEOUT_SEC = 6.0

# Aylık ücretsiz limiti (10k/ay) korumak için coingecko'ya özel min-refetch
# aralığı. Bu, ağ çağrısını seyrekleştirir ama içeride GERÇEK son barları
# tutar — başarısızlıkta bayat-veri 'fallback'ı DEĞİL, normal rate-limit cache.
# yfinance OHLCV bundan etkilenmez (ayrı provider).
_DEFAULT_OHLCV_TTL_SEC = 2400
_THROTTLE_LOCK = threading.Lock()
_BARS_CACHE: dict[tuple[str, str], tuple[float, list[OHLCVBar]]] = {}


def _ohlcv_ttl_sec() -> float:
    try:
        return float(os.environ.get("COINGECKO_OHLCV_TTL_SEC", _DEFAULT_OHLCV_TTL_SEC))
    except (TypeError, ValueError):
        return float(_DEFAULT_OHLCV_TTL_SEC)

_SYMBOL_MAP = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}

SUPPORTED = custom_assets.DynamicSymbolSet(frozenset(_SYMBOL_MAP.keys()), "coingecko")

# TF → (days, bucket_seconds, source etiketi)
_TF_PLAN: dict[str, tuple[int, int, str]] = {
    "15m": (1, 900, "resampled:coingecko_5m"),
    "1h": (90, 3600, "coingecko"),
    "1d": (365, 86400, "coingecko"),
}

NATIVE_TFS = frozenset(_TF_PLAN.keys())


def _fetch_prices(cg_id: str, days: int) -> list[tuple[float, float]] | None:
    url = f"{API}/{cg_id}/market_chart?vs_currency=usd&days={days}"
    req = urllib.request.Request(url, headers=coingecko_auth.headers())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    prices = data.get("prices")
    if not isinstance(prices, list) or not prices:
        return None
    out: list[tuple[float, float]] = []
    for row in prices:
        try:
            ts_ms, px = float(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        out.append((ts_ms / 1000.0, px))
    return out or None


def _points_to_bars(
    symbol: str,
    timeframe: Timeframe,
    points: list[tuple[float, float]],
    bucket_sec: int,
    source: str,
) -> list[OHLCVBar]:
    groups: dict[int, list[float]] = {}
    for epoch, px in sorted(points):
        groups.setdefault(int(epoch) // bucket_sec * bucket_sec, []).append(px)
    bars: list[OHLCVBar] = []
    for start in sorted(groups):
        pxs = groups[start]
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                ts=datetime.fromtimestamp(start, tz=UTC),
                open=pxs[0],
                high=max(pxs),
                low=min(pxs),
                close=pxs[-1],
                volume=None,
                source=source,
                verified=True,
            )
        )
    return bars


def get_bars(symbol: str, timeframe: Timeframe) -> list[OHLCVBar] | None:
    cg_id = _SYMBOL_MAP.get(symbol) or custom_assets.ticker_for(symbol, "coingecko")
    if cg_id is None:
        return None
    return fetch_by_ticker(cg_id, symbol, timeframe)


def fetch_by_ticker(cg_id: str, symbol: str, timeframe: Timeframe) -> list[OHLCVBar] | None:
    """`_SYMBOL_MAP`'i atlayıp doğrudan CoinGecko id'si ile çeker — yeni asset
    eklenmeden önce id'yi doğrulamak (probe) için kullanılır."""
    plan = _TF_PLAN.get(timeframe)
    if plan is None:
        return None
    key = (symbol, timeframe)
    ttl = _ohlcv_ttl_sec()
    now = time.monotonic()
    with _THROTTLE_LOCK:
        cached = _BARS_CACHE.get(key)
        if cached and (now - cached[0]) < ttl:
            return cached[1]
    days, bucket_sec, source = plan
    points = _fetch_prices(cg_id, days)
    if points is None:
        return None
    bars = _points_to_bars(symbol, timeframe, points, bucket_sec, source)
    # Yalnızca gerçek/taze sonucu cache'le — None cache'lenmez (stale fallback YOK).
    if bars:
        with _THROTTLE_LOCK:
            _BARS_CACHE[key] = (now, bars)
    return bars
