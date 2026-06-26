from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.volume import engine


def _bar(i: int, o: float, h: float, l: float, c: float, v: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST",
        timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def test_insufficient_bars_is_unavailable():
    result = engine.analyze([], timeframe="1d")
    assert result.validity == "unavailable"
    assert result.state == "VOLUME_NEUTRAL"


def test_volume_climax_detected():
    bars = [_bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000) for i in range(15)]
    bars[-1] = _bar(14, 113, 118, 112, 117, 5000)
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "VOLUME_CLIMAX"
    assert result.volume_ratio == 5.0


def test_volume_confirmation_when_above_average_and_aligned():
    bars = [_bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000) for i in range(15)]
    bars[-1] = _bar(14, 113, 116, 112, 115, 1300)  # ratio 1.3 (>=1.2), up, trend up
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "VOLUME_CONFIRMATION"


def test_volume_weakening_when_below_average_trend_continues():
    bars = [_bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000) for i in range(15)]
    bars[-1] = _bar(14, 113, 114, 112, 113.5, 500)  # ratio 0.5 (<=0.7), trend continues up
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "VOLUME_WEAKENING"


def test_volume_conflict_when_high_volume_against_trend():
    bars = [_bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000) for i in range(15)]
    bars[-1] = _bar(14, 113, 114, 105, 106, 1300)  # ratio 1.3, down candle, trend up
    result = engine.analyze(bars, timeframe="1d")
    assert result.state == "VOLUME_CONFLICT"


def test_missing_volume_is_weak_not_crash():
    bars = [_bar(i, 100, 101, 99, 100, None) for i in range(15)]  # type: ignore[arg-type]
    result = engine.analyze(bars, timeframe="1d")
    assert result.validity == "weak"
