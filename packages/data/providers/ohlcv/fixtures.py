"""Fixture OHLCV barları — YALNIZCA test/dev path (TEST_USE_MOCK).

Runtime'da asla kullanılmaz (DATA_POLICY: runtime'da mock veri yok).
Deterministik sinüs + hafif trend serisi üretir; indikatörlerin gerçek
hesapla (RSI/MACD/ATR/EMA) anlamlı değerler vermesi için yeterli bar
(default 260) sağlar. Tüm barlar `source="fixture"`, `verified=False`.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar, Timeframe

TF_SECONDS: dict[Timeframe, int] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

_BASELINE = {
    "BTCUSD": 68_000.0,
    "ETHUSD": 3_500.0,
    "XAUUSD": 2_350.0,
    "XAGUSD": 28.0,
    "BRENT": 82.0,
    "DXY": 104.0,
    "US10Y": 4.3,
    "VIX": 14.0,
    "QQQ": 460.0,
    "SP500": 5_300.0,
}


def _phase(symbol: str, timeframe: str) -> int:
    h = hashlib.sha1(f"{symbol}|{timeframe}".encode()).hexdigest()[:8]
    return int(h, 16) % 360


def get_bars(symbol: str, timeframe: Timeframe, n: int = 260) -> list[OHLCVBar]:
    base = _BASELINE.get(symbol, 100.0)
    step = TF_SECONDS[timeframe]
    now = datetime.now(UTC)
    aligned = datetime.fromtimestamp(
        (int(now.timestamp()) // step) * step, tz=UTC
    )
    phase = _phase(symbol, timeframe)
    bars: list[OHLCVBar] = []
    prev_close = base
    for i in range(n):
        # Sinüs dalgası + hafif yukarı trend → RSI/MACD 0-100 uçlarına yapışmaz.
        wave = 0.04 * math.sin((i + phase) / 9.0)
        trend = 0.0002 * i
        close = round(base * (1.0 + wave + trend), 6)
        o = prev_close
        h = max(o, close) * 1.001
        lo = min(o, close) * 0.999
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                ts=aligned - timedelta(seconds=step * (n - 1 - i)),
                open=round(o, 6),
                high=round(h, 6),
                low=round(lo, 6),
                close=close,
                volume=1_000.0 + i,
                source="fixture",
                verified=False,
            )
        )
        prev_close = close
    return bars
