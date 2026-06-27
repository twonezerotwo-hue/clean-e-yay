"""packages/elliott/engine.py — Elliott Wave Scenario Engine testleri.

Kapsam: hard-rule ihlali olduğunda (NO_VALID_COUNT) sayımın nereden
başladığı (P0: bar/fiyat) ve hangi kuralın hangi değerlere göre ihlal
edildiği diagnostics'te AÇIKÇA görünmeli — uydurma "hard_rules_failed"
tek satırı yeterli değil (dashboard'da Layer 2'de bu eksiklik fark edildi).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.types import OHLCVBar
from packages.elliott import engine


def _bars(values: list[float]) -> list[OHLCVBar]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol="TESTXYZ", timeframe="1d", ts=base + timedelta(days=i),
            open=v, high=v, low=v, close=v, volume=100.0,
        )
        for i, v in enumerate(values)
    ]


def test_valid_impulse_count_includes_start_diagnostic():
    bars = _bars([108, 100, 110, 105, 125, 115, 130, 120])
    result = engine.analyze(bars, timeframe="1d", pivot_left=1, pivot_right=1)
    assert result.primary_scenario == "IMPULSE_1_2_3_4_5"
    assert result.wave_points[0].label == "P0"
    assert result.wave_points[0].price == 100.0
    assert result.wave_points[0].bar_index == 1
    assert any("Sayım P0'dan başladı" in d for d in result.diagnostics)
    assert "bar #1" in result.diagnostics[0]
    assert "100.0000" in result.diagnostics[0]


def test_wave2_breach_rejected_with_explicit_values():
    # P0=100, P1=110, P2=95 (P0'ı geçti — Wave 2 ihlali), P3=125, P4=115, P5=120
    # (P5=120 < P3=125 olduğu için ABC fallback'i de c_extends_beyond_a'da düşer)
    bars = _bars([105, 100, 110, 95, 125, 115, 120, 110])
    result = engine.analyze(bars, timeframe="1d", pivot_left=1, pivot_right=1)
    assert result.primary_scenario == "NO_VALID_COUNT"
    joined = " | ".join(result.diagnostics)
    # Sayımın nereden başladığı açık olmalı
    assert "Sayım P0'dan başladı" in joined
    assert "bar #1" in joined
    assert "100.0000" in joined
    # Hangi kural, hangi değerlere göre ihlal edildi açık olmalı
    assert "Wave 2 kuralı ihlal" in joined
    assert "95.0000" in joined  # P2 değeri
    # ABC fallback denemesinin de neden düştüğü görünmeli
    assert "C dalgası A'nın ötesine uzanmadı" in joined
    assert "120.0000" in joined  # C değeri
    assert "125.0000" in joined  # A değeri


def test_wave4_overlap_rejected_with_explicit_values():
    # P0=100, P1=110, P2=105, P3=125, P4=108 (P1=110 bölgesine girdi — overlap);
    # P5=120 < P3=125 olduğu için ABC fallback'i de c_extends_beyond_a'da düşer.
    bars = _bars([105, 100, 110, 105, 125, 108, 120, 110])
    result = engine.analyze(bars, timeframe="1d", pivot_left=1, pivot_right=1)
    assert result.primary_scenario == "NO_VALID_COUNT"
    joined = " | ".join(result.diagnostics)
    assert "Wave 4 overlap kuralı ihlal" in joined
    assert "108.0000" in joined  # P4
    assert "110.0000" in joined  # P1


def test_insufficient_pivots_is_explicit():
    bars = _bars([100, 101, 102])
    result = engine.analyze(bars, timeframe="1d", pivot_left=3, pivot_right=3)
    assert result.primary_scenario == "NO_VALID_COUNT"
    assert result.diagnostics == ["insufficient_pivots"]
    assert result.wave_points == []


def test_rejected_count_still_carries_wave_points_for_dashboard():
    """Reddedilen sayım bile wave_points taşımalı — dashboard P0..P5'i
    gösterebilsin, sadece 'hard rules failed' yazıp pivot bilgisini atmasın."""
    bars = _bars([105, 100, 110, 95, 125, 115, 120, 110])
    result = engine.analyze(bars, timeframe="1d", pivot_left=1, pivot_right=1)
    assert len(result.wave_points) > 0
    assert result.wave_points[0].label == "P0"
    assert result.wave_points[0].bar_index == 1
