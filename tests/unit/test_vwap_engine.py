from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.vwap import engine


def _bar(i: int, c: float, v: float = 1000) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST",
        timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=c,
        high=c + 1,
        low=c - 1,
        close=c,
        volume=v,
    )


def test_insufficient_bars_is_unavailable():
    result = engine.analyze([], timeframe="1d")
    assert result.validity == "unavailable"


def test_price_above_vwap_location():
    bars = [_bar(i, 100) for i in range(15)]
    result = engine.analyze(bars, timeframe="1d", current_price=120.0)
    assert result.location == "above"
    assert result.session_vwap is not None
    assert result.deviation_pct is not None and result.deviation_pct > 0


def test_anchored_levels_present_with_enough_bars():
    bars = [_bar(i, 100 + i) for i in range(15)]
    result = engine.analyze(bars, timeframe="1d", current_price=114.0)
    assert result.validity == "sane"
    anchors = {a.anchor for a in result.anchored}
    assert "major_high" in anchors
    assert "major_low" in anchors


def test_missing_volume_is_weak():
    bars = [
        OHLCVBar(
            symbol="TEST", timeframe="1d",
            ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
            open=100, high=101, low=99, close=100, volume=None,
        )
        for i in range(15)
    ]
    result = engine.analyze(bars, timeframe="1d")
    assert result.validity == "weak"
