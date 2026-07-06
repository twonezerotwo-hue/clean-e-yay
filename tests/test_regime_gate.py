"""regime_gate sinyali testleri (R1 — hava ölçer, EVIDENCE only).

Kritik güvenceler: (1) UP/DOWN tespiti doğru, (2) ER 0..1 bandında ve anlamlı
(düz çizgi ~1, testere ~0), (3) yetersiz veri → None (uydurma yok), (4) karne
ve v2 lean-seti bu sinyali AYNI isimle içerir (1:1 bütünlük).
"""
from __future__ import annotations

import math

from packages.signals import regime_gate as rg


def test_up_regime_on_rising_series():
    closes = [100 + i * 0.5 for i in range(80)]
    out = rg.assess(closes)
    assert out is not None
    assert out.regime == "UP" and out.lean == 1.0


def test_down_regime_on_falling_series():
    closes = [100 - i * 0.5 for i in range(80)]
    out = rg.assess(closes)
    assert out is not None
    assert out.regime == "DOWN" and out.lean == -1.0


def test_insufficient_history_returns_none():
    assert rg.assess([100.0] * rg.LOOKBACK) is None  # LOOKBACK+1 gerekir
    assert rg.lean([100.0] * 10) is None


def test_er_high_on_straight_line_low_on_chop():
    straight = [100 + i for i in range(80)]
    chop = [100 + (1 if i % 2 else -1) for i in range(80)]  # 99↔101 testere
    er_straight = rg.assess(straight).er
    er_chop = rg.assess(chop).er
    assert 0.0 <= er_chop <= 1.0 and 0.0 <= er_straight <= 1.0
    assert er_straight > 0.9      # düz çizgi = tam verimli trend
    assert er_chop < 0.2          # testere = verimsiz


def test_flat_series_is_up_with_zero_er():
    """Sabit seri: eşitlik → UP (belgeli kural), yol=0 → er=0 (bölme hatası yok)."""
    out = rg.assess([100.0] * 80)
    assert out is not None
    assert out.regime == "UP" and out.er == 0.0


def test_wave_regime_matches_net_direction():
    """Dalgalı ama net yukarı seri → UP (dalga kandırmaz, net yön belirler)."""
    closes = [100 + i * 0.3 + 2.0 * math.sin(i / 4.0) for i in range(90)]
    assert rg.assess(closes).regime == "UP"


def test_karne_and_v2_lean_sets_include_regime_gate():
    """1:1 bütünlük: karne ölçtüğü kümeyle v2'nin lean kümesi aynı — regime_gate
    ikisinde de 'regime_gate' adıyla var (kural 3: eklenen sinyal tüketiliyor)."""
    from datetime import UTC, datetime, timedelta

    from packages.data.types import OHLCVBar
    from packages.scoring import tf_scoring_v2 as v2

    base = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(260):
        px = 100 + i * 0.4 + 2.0 * math.sin(i / 4.0)
        bars.append(OHLCVBar(symbol="X", timeframe="1d", ts=base + timedelta(days=i),
                             open=px, high=px * 1.01, low=px * 0.99, close=px,
                             volume=1.0))
    leans = v2.collect_leans("1d", bars)
    assert "regime_gate" in leans and leans["regime_gate"] == 1.0
