"""Read-only, real-candle Kraken spot OHLCV provider.

This module never places orders and needs no private key.
The current unfinished candle is always discarded.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from packages.data.types import OHLCVBar, Timeframe

ENDPOINT = "https://api.kraken.com/0/public/OHLC"

PAIRS = {
    "BTCUSD": "XBTUSD",
    "ETHUSD": "ETHUSD",
}

INTERVALS = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def enabled_for(symbol: str) -> bool:
    flag = os.environ.get(
        "EYAY_KRAKEN_OHLCV_ENABLED", "false"
    ).strip().lower()

    return flag in {"1", "true", "yes", "on"} and symbol in PAIRS


def _fetch(symbol: str, timeframe: Timeframe) -> dict:
    query = urllib.parse.urlencode({
        "pair": PAIRS[symbol],
        "interval": INTERVALS[timeframe],
    })

    request = urllib.request.Request(
        f"{ENDPOINT}?{query}",
        headers={
            "User-Agent": "EYAY-OHLCV/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def _parse(
    payload: dict,
    symbol: str,
    timeframe: Timeframe,
    *,
    now: datetime | None = None,
) -> list[OHLCVBar]:
    now = now or datetime.now(UTC)

    if payload.get("error"):
        return []

    result = payload.get("result")

    if not isinstance(result, dict):
        return []

    candidates = [
        value
        for key, value in result.items()
        if key != "last" and isinstance(value, list)
    ]

    if len(candidates) != 1:
        return []

    rows = candidates[0]

    if len(rows) < 2:
        return []

    seconds = INTERVALS[timeframe] * 60
    candles: dict[datetime, OHLCVBar] = {}

    # Kraken's final row is an unfinished candle.
    for row in rows[:-1]:
        try:
            if len(row) < 8:
                continue

            stamp = datetime.fromtimestamp(
                int(float(row[0])),
                tz=UTC,
            )

            o = float(row[1])
            h = float(row[2])
            low = float(row[3])
            c = float(row[4])
            volume = float(row[6])

            values = (o, h, low, c, volume)

            if not all(math.isfinite(x) for x in values):
                continue

            if min(o, h, low, c) <= 0 or volume < 0:
                continue

            if not (
                low <= min(o, c)
                and h >= max(o, c)
                and low <= h
            ):
                continue

            if stamp.timestamp() + seconds > now.timestamp():
                continue

            candles[stamp] = OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                ts=stamp,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=volume,
                source="kraken_spot",
                verified=True,
            )

        except (ValueError, TypeError, IndexError, OverflowError):
            continue

    return [candles[t] for t in sorted(candles)]


def get_bars(
    symbol: str,
    timeframe: Timeframe,
) -> list[OHLCVBar] | None:
    if not enabled_for(symbol):
        return None

    if timeframe not in INTERVALS:
        return None

    try:
        payload = _fetch(symbol, timeframe)
        bars = _parse(payload, symbol, timeframe)
    except Exception:
        # Provider boundary: an unexpected public-API/decoder error must mark
        # this source unavailable so the orchestrator can use its next source
        # or an explicitly degraded cache, never crash a snapshot.
        return None

    # Do not upgrade a technical timeframe unless its
    # minimum history requirement is satisfied.
    if len(bars) < 200:
        return None

    return bars
