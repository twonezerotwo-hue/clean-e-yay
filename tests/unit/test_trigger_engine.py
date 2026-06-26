from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import LiquiditySweepAnalysis, OHLCVBar, VolumeAnalysis, VWAPAnalysis
from packages.scoring import trigger


def _bar(i: int, o: float, h: float, l: float, c: float, v: float = 1000) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=o, high=h, low=l, close=c, volume=v,
    )


def test_insufficient_bars_is_unavailable():
    result = trigger.analyze([], timeframe="1d")
    assert result.validity == "unavailable"
    assert result.state == "TRIGGER_MISSING"


def test_bullish_engulfing_detected():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 110, 111, 105, 106), _bar(2, 105, 115, 104, 113)]
    result = trigger.analyze(bars, timeframe="1d")
    assert "engulfing_bullish" in result.matched_triggers
    assert result.trigger_score >= 30.0


def test_bearish_engulfing_detected():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 100, 110, 99, 109), _bar(2, 111, 112, 95, 96)]
    result = trigger.analyze(bars, timeframe="1d")
    assert "engulfing_bearish" in result.matched_triggers


def test_bullish_pin_bar_detected():
    # body=4.5 (100->104.5), lower_wick=10 (>=body*2), upper_wick=0.5 (<body) → bullish pin bar.
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 105, 90, 104.5)]
    result = trigger.analyze(bars, timeframe="1d")
    assert "pin_bar_bullish" in result.matched_triggers


def test_full_confluence_confirms_trigger():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 110, 111, 105, 106), _bar(2, 105, 115, 104, 113, v=2000)]
    volume = VolumeAnalysis(timeframe="1d", state="VOLUME_CONFIRMATION", price_direction="up", validity="sane")
    vwap = VWAPAnalysis(timeframe="1d", reclaim=True, validity="sane")
    sweep = LiquiditySweepAnalysis(timeframe="1d", state="LOW_SWEEP_RECLAIMED", validity="sane")
    result = trigger.analyze(bars, timeframe="1d", volume=volume, vwap=vwap, sweep=sweep)
    assert result.state == "TRIGGER_CONFIRMED"
    assert result.trigger_score == 85.0  # engulfing(30)+volume(20)+vwap(15)+sweep(20)


def test_volume_conflict_against_pattern_yields_failed():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 110, 111, 105, 106), _bar(2, 105, 115, 104, 113)]
    volume = VolumeAnalysis(timeframe="1d", state="VOLUME_CONFLICT", price_direction="down", validity="sane")
    result = trigger.analyze(bars, timeframe="1d", volume=volume)
    assert result.state == "TRIGGER_FAILED"


def test_no_pattern_no_evidence_is_missing():
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100), _bar(2, 100, 101, 99, 100)]
    result = trigger.analyze(bars, timeframe="1d")
    assert result.state == "TRIGGER_MISSING"
    assert result.matched_triggers == []
