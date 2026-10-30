"""Read-only, real-candle Binance spot OHLCV provider (owner kararı 2026-10-30).

Anahtar gerekmez, emir vermez. Yalnız piyasa verisi ucu (data-api.binance.vision)
kullanılır. Bitmemiş mum her zaman atılır. Kripto barlarının CoinGecko'ya (aylık
10.000 çağrı) bağımlılığını kaldırır: BTC/ETH'de Kraken'den sonra ikinci, DODO gibi
özel kripto varlıklarda birincil gerçek-mum kaynağıdır. Binance'te listelenmeyen
sembol bir gün boyunca yeniden sorulmaz.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from packages.data.registry import custom_assets
from packages.data.types import OHLCVBar, Timeframe

ENDPOINT = "https://data-api.binance.vision/api/v3/klines"

PAIRS = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
}

INTERVALS = {
    "15m": ("15m", 15),
    "1h": ("1h", 60),
    "4h": ("4h", 240),
    "1d": ("1d", 1440),
    "1w": ("1w", 10080),
}

MIN_BARS = 200
_UNLISTED_TTL_SEC = 86400.0
_UNLISTED: dict[str, float] = {}
_LOCK = threading.Lock()


def pair_for(symbol: str) -> str | None:
    if symbol in PAIRS:
        return PAIRS[symbol]
    ticker = custom_assets.ticker_for(symbol, "coingecko")
    if ticker is None:
        return None  # yalnız kripto varlıklar
    return f"{symbol.upper()}USDT"


def enabled_for(symbol: str) -> bool:
    flag = os.environ.get("EYAY_BINANCE_OHLCV_ENABLED", "false").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    pair = pair_for(symbol)
    if pair is None:
        return False
    with _LOCK:
        until = _UNLISTED.get(pair)
    return until is None or until < time.monotonic()


def _fetch(pair: str, timeframe: Timeframe) -> list:
    interval, _minutes = INTERVALS[timeframe]
    query = urllib.parse.urlencode({"symbol": pair, "interval": interval, "limit": 1000})
    request = urllib.request.Request(
        f"{ENDPOINT}?{query}",
        headers={"User-Agent": "EYAY-OHLCV/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def _parse(rows: list, symbol: str, timeframe: Timeframe, *, now: datetime | None = None) -> list[OHLCVBar]:
    now = now or datetime.now(UTC)
    _interval, minutes = INTERVALS[timeframe]
    seconds = minutes * 60
    candles: dict[datetime, OHLCVBar] = {}
    for row in rows if isinstance(rows, list) else []:
        try:
            if len(row) < 7:
                continue
            stamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
            o, h, low, c, volume = (float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            if not all(math.isfinite(x) for x in (o, h, low, c, volume)):
                continue
            if min(o, h, low, c) <= 0 or volume < 0:
                continue
            if not (low <= min(o, c) and h >= max(o, c) and low <= h):
                continue
            # Bitmemiş mum: kapanış zamanı henüz gelmedi.
            if stamp.timestamp() + seconds > now.timestamp():
                continue
            candles[stamp] = OHLCVBar(
                symbol=symbol, timeframe=timeframe, ts=stamp,
                open=o, high=h, low=low, close=c, volume=volume,
                source="binance_spot", verified=True,
            )
        except (ValueError, TypeError, IndexError, OverflowError):
            continue
    return [candles[t] for t in sorted(candles)]


def get_bars(symbol: str, timeframe: Timeframe) -> list[OHLCVBar] | None:
    if not enabled_for(symbol) or timeframe not in INTERVALS:
        return None
    pair = pair_for(symbol)
    if pair is None:
        return None
    try:
        rows = _fetch(pair, timeframe)
        bars = _parse(rows, symbol, timeframe)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:  # "Invalid symbol": Binance'te listelenmiyor
            with _LOCK:
                _UNLISTED[pair] = time.monotonic() + _UNLISTED_TTL_SEC
        return None
    except Exception:
        # Sağlayıcı sınırı: beklenmeyen bir hata snapshot'ı düşürmez; router sıradaki
        # kaynağa ya da açıkça bayat önbelleğe geçer.
        return None
    if len(bars) < MIN_BARS:
        return None
    return bars


def reset_cache() -> None:
    with _LOCK:
        _UNLISTED.clear()
