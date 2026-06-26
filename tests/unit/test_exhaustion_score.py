from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar, VolumeAnalysis
from packages.scoring import exhaustion


def _bar(i: int, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def test_insufficient_bars_is_unavailable():
    result = exhaustion.analyze([], timeframe="1d")
    assert result.validity == "unavailable"
    assert result.score == 50.0


def test_strong_uptrend_pushes_score_toward_upside_exhaustion():
    bars = [_bar(i, 100 + i * 3) for i in range(25)]
    result = exhaustion.analyze(bars, timeframe="1d")
    assert result.score > 50.0
    assert any("rsi_extreme_high" in c or "extended_up_return" in c for c in result.contributions)


def test_strong_downtrend_pushes_score_toward_downside_exhaustion():
    bars = [_bar(i, 200 - i * 3) for i in range(25)]
    result = exhaustion.analyze(bars, timeframe="1d")
    assert result.score < 50.0


def test_flat_market_stays_neutral():
    bars = [_bar(i, 100) for i in range(25)]
    result = exhaustion.analyze(bars, timeframe="1d")
    assert result.score == 50.0


def test_volume_climax_up_adds_upside_contribution():
    bars = [_bar(i, 100) for i in range(25)]
    vol = VolumeAnalysis(timeframe="1d", state="VOLUME_CLIMAX", price_direction="up", validity="sane")
    result = exhaustion.analyze(bars, timeframe="1d", volume=vol)
    assert result.score > 50.0
    assert "volume_climax_up" in result.contributions
