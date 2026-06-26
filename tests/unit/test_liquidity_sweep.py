from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.liquidity import sweep as engine


def _bar(i: int, o: float, h: float, l: float, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST",
        timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000,
    )


def test_insufficient_bars_is_unavailable():
    result = engine.analyze([], timeframe="1d")
    assert result.validity == "unavailable"
    assert result.state == "NO_SWEEP"


def test_no_sweep_when_price_stays_in_range():
    bars = [_bar(i, 100, 105, 95, 100) for i in range(20)]
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "NO_SWEEP"


def test_low_sweep_reclaimed_is_bullish():
    bars = [_bar(i, 100, 105, 95, 100) for i in range(30)]
    bars += [_bar(30 + j, 100, 102, 98, 100) for j in range(3)]
    bars.append(_bar(34, 100, 101, 90, 101))  # sweeps below 95, closes back above
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "LOW_SWEEP_RECLAIMED"
    assert result.bias == "REVERSAL_LONG"
    assert result.swing_low == 95.0


def test_high_sweep_reclaimed_is_bearish():
    bars = [_bar(i, 100, 105, 95, 100) for i in range(30)]
    bars += [_bar(30 + j, 100, 102, 98, 100) for j in range(3)]
    bars.append(_bar(34, 100, 110, 99, 99))  # sweeps above 105, closes back below
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "HIGH_SWEEP_RECLAIMED"
    assert result.bias == "REVERSAL_SHORT"
    assert result.swing_high == 105.0


def test_low_sweep_pending_when_not_yet_reclaimed():
    bars = [_bar(i, 100, 105, 95, 100) for i in range(30)]
    bars += [_bar(30 + j, 100, 102, 98, 100) for j in range(3)]
    bars.append(_bar(34, 100, 96, 90, 92))  # sweeps below 95, closes still below
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "LOW_SWEEP_PENDING"
    assert result.bias == "unknown"
