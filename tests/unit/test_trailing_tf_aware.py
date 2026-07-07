"""TF-farkında trailing testleri (çıkış otopsisi + exit_backtest düzeltmesi).

- `tf_trailing_mults`: flag OFF → (1.0,1.0) bayt-aynı; ON → TF profili (2026-07-07
  REVİZE: higher TF trail SIKILIR, <1.0); bilinmeyen TF → (1.0,1.0); guardrail
  [0.4,4.0] (sıkabilir de gevşetebilir de; taban 0.4).
- open_position: flag OFF → trailing düz değer birebir; ON → düz × TF-çarpanı.
- Eski (düz) değerler OPENED audit'inde shadow olarak yan yana.
"""
from __future__ import annotations

import pytest

from packages.data.registry.loader import threshold_override
from packages.paper import lifecycle as L
from packages.paper import state as S
from packages.risk import trade_economics as te

_ON = {"trailing_tf_aware": {"enabled": True}}
_OFF = {"trailing_tf_aware": {"enabled": False}}


# ── tf_trailing_mults ────────────────────────────────────────────────────────

def test_mults_flag_off_is_neutral():
    with threshold_override(_OFF):
        assert te.tf_trailing_mults("4h") == (1.0, 1.0)
        assert te.tf_trailing_mults("1d") == (1.0, 1.0)


def test_mults_flag_on_tightens_higher_tf():
    # REVİZE (exit_backtest): higher-TF trail SIKILIR (<1.0), erken devreye.
    with threshold_override(_ON):
        assert te.tf_trailing_mults("15m") == (1.0, 1.0)   # kısa TF dokunulmaz
        assert te.tf_trailing_mults("1h") == (0.8, 1.0)
        assert te.tf_trailing_mults("4h") == (0.7, 1.0)    # en çok SIKILAN (worst offender)
        assert te.tf_trailing_mults("1d") == (0.7, 1.0)


def test_mults_unknown_tf_neutral():
    with threshold_override(_ON):
        assert te.tf_trailing_mults("3m") == (1.0, 1.0)


def test_mults_guardrail_clamps_both_ends():
    # Guardrail [0.4,4.0]: aşırı değerler kırpılır (99→tavan 4, 0.2→taban 0.4).
    cfg = {"trailing_tf_aware": {"enabled": True, "tf_profile": {
        "4h": {"distance_mult": 99.0, "activate_mult": 0.2}}}}
    with threshold_override(cfg):
        d, a = te.tf_trailing_mults("4h")
        assert d == 4.0 and a == 0.4   # 99→4 (tavan), 0.2→0.4 (taban)


# ── open_position kablolama ──────────────────────────────────────────────────

def test_open_flag_off_trailing_is_flat():
    ps = S._initial_state()
    with threshold_override(_OFF):
        pos = L.open_position(ps, symbol="BTCUSD", side="long", entry_price=100.0,
                              size_multiplier=1.0, predicted_confidence=0.50, timeframe="4h")
    # STRONG tier trail_distance 0.020 × 1.0 × 1.0 = 0.020; activate 0.01 × 1.0.
    assert pos.trail_distance_pct == pytest.approx(0.020)
    assert pos.trail_activate_pct == pytest.approx(0.01)


def test_open_flag_on_trailing_tightened():
    ps = S._initial_state()
    with threshold_override(_ON):
        pos = L.open_position(ps, symbol="BTCUSD", side="long", entry_price=100.0,
                              size_multiplier=1.0, predicted_confidence=0.50, timeframe="4h")
    # STRONG 0.020 × 0.7 (4h distance, SIKILDI) = 0.014; activate 0.01 × 1.0 = 0.01.
    assert pos.trail_distance_pct == pytest.approx(0.014)
    assert pos.trail_activate_pct == pytest.approx(0.01)


def test_open_records_flat_shadow_in_audit():
    from packages.paper import audit
    ps = S._initial_state()
    with threshold_override(_ON):
        L.open_position(ps, symbol="BTCUSD", side="long", entry_price=100.0,
                        size_multiplier=1.0, predicted_confidence=0.50, timeframe="4h")
    rec = audit.read_recent(1)[-1]
    assert rec["action"] == "OPENED"
    assert rec["trail_distance_used"] == 0.014 and rec["trail_distance_flat"] == 0.02
    assert rec["trail_activate_used"] == 0.01 and rec["trail_activate_flat"] == 0.01
