"""F5 — EV (beklenen değer) kapısı + Kelly sizing yardımcıları (pure)."""
from __future__ import annotations

import pytest

from packages.decision import engine as e


def test_expected_value_math():
    # p=0.48, RR=2.0, cost=0.1 → 0.96 − 0.52 − 0.1 = 0.34 (pozitif)
    assert e._expected_value(0.48, 2.0, 0.1) == pytest.approx(0.34)
    # p=0.35, RR=1.5, cost=0.1 → 0.525 − 0.65 − 0.1 = −0.225 (NEGATİF EV → açma)
    assert e._expected_value(0.35, 1.5, 0.1) == pytest.approx(-0.225)


def test_kelly_fraction_math_and_clamp():
    # p=0.55, RR=2.0 → (1.1 − 0.45)/2 = 0.325
    assert e._kelly_fraction(0.55, 2.0) == pytest.approx(0.325)
    # zayıf edge → negatif → 0'a clamp
    assert e._kelly_fraction(0.30, 1.0) == 0.0
    # rr<=0 → 0 (güvenli)
    assert e._kelly_fraction(0.6, 0.0) == 0.0


def test_kelly_scales_with_edge():
    # Daha güçlü p(win) → daha büyük Kelly oranı (edge'e oransal).
    assert e._kelly_fraction(0.60, 2.0) > e._kelly_fraction(0.50, 2.0)


def test_tf_rr_reads_config():
    assert e._tf_rr("4h") == pytest.approx(2.0)
    assert e._tf_rr("1d") == pytest.approx(2.5)
    assert e._tf_rr("unknown_tf") == pytest.approx(2.0)  # fallback
