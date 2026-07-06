"""Market structure sinyali v2 (HH/HL + BOS/CHoCH + olgunluk) testleri — SAF.

Kurgu: 9 düz bar (pivot üretmez) + belirli tepe/dip dizisi → analyze()'ın
trend/BOS/CHoCH/streak okumasını doğrula. Yetersiz veri (<20 bar / <2'şer
pivot) → None (uydurma yok).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.signals import market_structure as ms


def _bar(i: int, h: float, low: float, c: float) -> OHLCVBar:
    return OHLCVBar(
        symbol="TEST", timeframe="1d",
        ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=c, high=h, low=low, close=c, volume=100.0,
    )


_PAD = [(100.2, 99.8)] * 9  # düz — strict-fraktal pivot üretmez (≥20 bar için)

# yükseliş: tepe pivotları (109<113 HH), dip pivotları (94<96 HL)
_UP = [
    (101, 99), (102, 98), (100, 94), (104, 98), (109, 101),
    (105, 100), (104, 99), (103, 96), (107, 100), (113, 103),
    (109, 104), (108, 103),
]
# düşüş: tepe (114>110 LH), dip (95>90 LL)
_DOWN = [
    (108, 106), (107, 105), (114, 104), (106, 101), (104, 95),
    (108, 100), (109, 101), (110, 98), (103, 96), (101, 90),
    (104, 94), (103, 95),
]


def _bars(seq, closes=None):
    full = _PAD + list(seq)
    cl = [100.0] * len(_PAD) + (list(closes) if closes else [(h + low) / 2 for h, low in seq])
    return [_bar(i, h, low, cl[i]) for i, (h, low) in enumerate(full)]


def test_uptrend_bullish():
    m = ms.analyze(_bars(_UP, closes=[*([104] * 11), 105]))
    assert m is not None
    assert m.trend == "BULLISH"
    assert m.lean > 0
    assert m.bos == "none" and m.choch == "none"  # 105 tepeyi(113) kırmadı, dibi(96) delmedi
    assert m.legs >= 4  # temizlenmiş zigzag'da en az 2 tepe + 2 dip


def test_downtrend_bearish():
    m = ms.analyze(_bars(_DOWN, closes=[*([100] * 11), 98]))
    assert m is not None
    assert m.trend == "BEARISH"
    assert m.lean < 0


def test_bos_bullish_breaks_high():
    bars = _bars(_UP, closes=[*([104] * 11), 105])
    bars.append(_bar(len(bars), 116, 110, 115))  # close 115 > son tepe 113
    m = ms.analyze(bars)
    assert m is not None and m.trend == "BULLISH"
    assert m.bos == "bullish"
    assert m.lean > 0.4  # BOS devam sinyali (streak kısa → tam sönümsüz)


def test_choch_bearish_breaks_low():
    bars = _bars(_UP, closes=[*([104] * 11), 105])
    bars.append(_bar(len(bars), 97, 92, 93))  # close 93 < son dip 96
    m = ms.analyze(bars)
    assert m is not None and m.trend == "BULLISH"
    assert m.choch == "bearish"
    assert m.lean == -1.0  # CHoCH ASLA sönümlenmez (dönüş sinyali)


def test_choch_not_dampened_but_bos_is():
    """CHoCH tam ±1 kalır; BOS/trend olgunlukla sönümlenir (tükenme priori)."""
    bars = _bars(_UP, closes=[*([104] * 11), 105])
    bars.append(_bar(len(bars), 97, 92, 93))
    m = ms.analyze(bars)
    assert abs(m.lean) == 1.0  # choch sönümsüz


def test_insufficient_returns_none():
    assert ms.analyze([]) is None
    assert ms.analyze(_bars(_UP[:4])) is None  # <20 bar? pad(9)+4=13 <20 → None


def test_lean_wrapper():
    assert ms.lean([]) is None
    assert ms.lean(_bars(_UP, closes=[*([104] * 11), 105])) > 0
