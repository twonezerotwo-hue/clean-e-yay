"""RSI-Uç (fade) sinyali testleri — SAF, salt-gözlem.

Aşırı-alım → negatif (fade down), aşırı-satım → pozitif (fade up), ortada 0,
yetersiz veri → None. Uçtan uzaklaştıkça büyüklük artar.
"""
from __future__ import annotations

from packages.signals import rsi_extreme


def test_overbought_negative_fade():
    closes = [100 + i for i in range(30)]  # sürekli yükseliş → RSI yüksek (aşırı-alım)
    ln = rsi_extreme.lean(closes)
    assert ln is not None and ln < 0  # fade DOWN


def test_oversold_positive_fade():
    closes = [100 - i for i in range(30)]  # sürekli düşüş → RSI düşük (aşırı-satım)
    ln = rsi_extreme.lean(closes)
    assert ln is not None and ln > 0  # fade UP


def test_midrange_zero():
    # zikzak → RSI ~50, uç değil → 0
    closes = [100 + (1 if i % 2 else -1) for i in range(30)]
    ln = rsi_extreme.lean(closes)
    assert ln == 0.0


def test_insufficient_none():
    assert rsi_extreme.lean([100.0, 101.0]) is None


def test_polarity_is_inverse_of_linear():
    """Uçta polarite touche'un lineer lean'inin TERSİ olmalı: yükselişte RSI
    yüksek → lineer lean POZİTİF (al) ama fade NEGATİF (geri çekilme bekle)."""
    up = [100 + i for i in range(30)]
    down = [100 - i for i in range(30)]
    assert rsi_extreme.lean(up) < 0    # yükseliş uçta fade aşağı
    assert rsi_extreme.lean(down) > 0  # düşüş uçta fade yukarı


def test_magnitude_bounded():
    for closes in ([100 + i for i in range(30)], [100 - i for i in range(30)]):
        ln = rsi_extreme.lean(closes)
        assert -1.0 <= ln <= 1.0
