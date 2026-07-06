"""Candle-rejection sinyali testleri — SAF, salt-gözlem (candles.detect reuse).

Bullish rejeksiyon → +, bearish → −, engulfing ±1.0 > pin ±0.7, sinyal yok → None.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.signals import candle_rejection


def _bar(i: int, o: float, h: float, low: float, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=o, high=h, low=low, close=c, volume=100.0,
    )


_FILLER = _bar(0, 100, 101, 99, 100)


def test_bullish_engulfing_positive():
    # önceki kırmızı, son yeşil onu yutuyor → bullish_engulfing → +1.0
    bars = [_FILLER, _bar(1, 100, 100.5, 98.9, 99.0), _bar(2, 98.8, 101.5, 98.5, 101.0)]
    ln = candle_rejection.lean(bars)
    assert ln == 1.0


def test_bearish_engulfing_negative():
    # önceki yeşil, son kırmızı onu yutuyor → bearish_engulfing → −1.0
    bars = [_FILLER, _bar(1, 99.0, 101.5, 98.5, 101.0), _bar(2, 101.2, 101.5, 98.4, 98.8)]
    ln = candle_rejection.lean(bars)
    assert ln == -1.0


def test_no_pattern_none():
    # iki benzer küçük bar → sinyal yok → None
    bars = [_FILLER, _bar(1, 100, 100.4, 99.7, 100.1), _bar(2, 100.1, 100.5, 99.8, 100.2)]
    assert candle_rejection.lean(bars) is None


def test_too_few_none():
    assert candle_rejection.lean([_FILLER]) is None
    assert candle_rejection.lean([]) is None


def test_magnitude_bounded():
    bars = [_FILLER, _bar(1, 100, 100.5, 98.9, 99.0), _bar(2, 98.8, 101.5, 98.5, 101.0)]
    ln = candle_rejection.lean(bars)
    assert ln is not None and -1.0 <= ln <= 1.0
