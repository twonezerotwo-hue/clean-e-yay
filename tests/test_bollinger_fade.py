"""Bollinger band-fade sinyali testleri — SAF, salt-gözlem.

Üst banda değme → −1 (fade down), alt banda → +1 (fade up), bant içi → 0,
düz seri (std=0) / yetersiz → None.
"""
from __future__ import annotations

from packages.signals import bollinger_fade


def test_upper_band_fades_down():
    # 20 bar ~100 dalgalı + son bar tepede (banda aşar) → fade down
    closes = [100 + (1 if i % 2 else -1) for i in range(20)] + [108.0]
    ln = bollinger_fade.lean(closes)
    assert ln == -1.0


def test_lower_band_fades_up():
    closes = [100 + (1 if i % 2 else -1) for i in range(20)] + [92.0]
    ln = bollinger_fade.lean(closes)
    assert ln == 1.0


def test_inside_band_zero():
    closes = [100 + (1 if i % 2 else -1) for i in range(20)] + [100.2]
    ln = bollinger_fade.lean(closes)
    assert ln == 0.0


def test_flat_series_none():
    # std=0 (düz) → bant yok → None (uydurma yok)
    assert bollinger_fade.lean([100.0] * 25) is None


def test_insufficient_none():
    assert bollinger_fade.lean([100.0, 101.0, 102.0]) is None


def test_bounded():
    for last in (200.0, 10.0):
        closes = [100 + (1 if i % 2 else -1) for i in range(20)] + [last]
        ln = bollinger_fade.lean(closes)
        assert ln is not None and -1.0 <= ln <= 1.0
