"""VWAP-fade sinyali testleri — SAF, salt-gözlem (vwap/engine reuse).

Intraday + aşırı sapma: üstte → −1 (fade down), altta → +1 (fade up).
Aşırı değil → 0. Intraday değil (1d) / yetersiz → None.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.signals import vwap_fade


def _bar(i: int, o: float, h: float, low: float, c: float, tf: str = "15m") -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe=tf,
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
        open=o, high=h, low=low, close=c, volume=100.0,
    )


def _flat(n: int, tf: str = "15m", level: float = 100.0):
    return [_bar(i, level, level + 0.5, level - 0.5, level, tf) for i in range(n)]


def test_extreme_above_fades_down():
    bars = _flat(30)
    bars.append(_bar(30, 100, 110.5, 100, 110))  # son fiyat VWAP'ın ~%10 üstü
    ln = vwap_fade.lean(bars, timeframe="15m")
    assert ln == -1.0  # fade DOWN


def test_extreme_below_fades_up():
    bars = _flat(30)
    bars.append(_bar(30, 100, 100, 89.5, 90))  # son fiyat VWAP'ın ~%10 altı
    ln = vwap_fade.lean(bars, timeframe="15m")
    assert ln == 1.0  # fade UP


def test_not_extreme_zero():
    bars = _flat(30)
    bars.append(_bar(30, 100, 100.6, 99.9, 100.3))  # küçük sapma → aşırı değil
    ln = vwap_fade.lean(bars, timeframe="15m")
    assert ln == 0.0


def test_non_intraday_none():
    bars = _flat(30, tf="1d")
    bars.append(_bar(30, 100, 110.5, 100, 110, tf="1d"))
    assert vwap_fade.lean(bars, timeframe="1d") is None  # VWAP intraday-only


def test_insufficient_none():
    assert vwap_fade.lean(_flat(2), timeframe="15m") is None
