"""Conflict Resolver (packages/decision/conflict_resolver.py) — saf fonksiyon testleri.

Otorite sırası (spec v2.3 §28.1) burada test edilir: hard safety her şeyi
ezer, blocked_by her zaman otorite sırasına göre dolu, conflict_resolution_path
her zaman kronolojik (12 adımın hepsi her zaman değerlendirilir).
"""
from __future__ import annotations

from packages.decision import conflict_resolver as cr

BASE = dict(
    dqs_status="OK",
    risk_gate_action="HOLD",
    trigger_confirmed=True,
    sl_tp_rr_valid=True,
    setup_type="TREND_LONG",
    historical_edge_strong_negative=False,
    size_multiplier=1.0,
    alignment_status="ALIGNED",
    elliott_scenario="NO_VALID_COUNT",
    elliott_confidence=0.0,
)


def _inputs(**overrides) -> cr.ConflictInputs:
    return cr.ConflictInputs(**{**BASE, **overrides})


def test_all_pass_yields_candidate_open():
    result = cr.resolve(_inputs())
    assert result.final_action == cr.CANDIDATE_OPEN
    assert result.blocked_by == []
    assert len(result.conflict_resolution_path) == 12


def test_dqs_bad_is_hard_blocked_regardless_of_other_evidence():
    result = cr.resolve(_inputs(dqs_status="BAD", setup_type="NO_TRADE", risk_gate_action="HOLD"))
    assert result.final_action == cr.BLOCKED
    assert result.blocked_by == ["hard_safety:BAD/HOLD"]
    # Hard safety en üst otorite — path'in tamamı koşulmaz (kısa devre).
    assert result.conflict_resolution_path == ["hard_safety:dqs=BAD,risk=HOLD"]


def test_kill_switch_is_hard_blocked():
    result = cr.resolve(_inputs(risk_gate_action="KILL_SWITCH"))
    assert result.final_action == cr.BLOCKED
    assert "hard_safety:OK/KILL_SWITCH" in result.blocked_by


def test_risk_gate_no_position_increase_blocks_to_no_trade():
    result = cr.resolve(_inputs(risk_gate_action="NO_POSITION_INCREASE"))
    assert result.final_action == cr.NO_TRADE
    assert "risk_gate:NO_POSITION_INCREASE" in result.blocked_by


def test_only_trigger_missing_yields_watch_not_no_trade():
    result = cr.resolve(_inputs(trigger_confirmed=False))
    assert result.final_action == cr.WATCH
    assert result.blocked_by == ["trigger_missing"]


def test_setup_invalid_blocks_to_no_trade():
    result = cr.resolve(_inputs(setup_type="NO_TRADE"))
    assert result.final_action == cr.NO_TRADE
    assert "setup_invalid" in result.blocked_by


def test_historical_edge_strong_negative_blocks():
    result = cr.resolve(_inputs(historical_edge_strong_negative=True))
    assert result.final_action == cr.NO_TRADE
    assert "historical_edge_strong_negative" in result.blocked_by


def test_zero_size_blocks():
    result = cr.resolve(_inputs(size_multiplier=0.0))
    assert result.final_action == cr.NO_TRADE
    assert "position_size_zero" in result.blocked_by


def test_conflicted_alignment_blocks():
    result = cr.resolve(_inputs(alignment_status="CONFLICTED"))
    assert result.final_action == cr.NO_TRADE
    assert "alignment_conflicted" in result.blocked_by


def test_dqs_degraded_with_everything_else_valid_yields_watch():
    result = cr.resolve(_inputs(dqs_status="DEGRADED"))
    assert result.final_action == cr.WATCH
    assert result.blocked_by == ["dqs_degraded"]


def test_multiple_failures_are_all_collected_in_authority_order():
    result = cr.resolve(
        _inputs(
            risk_gate_action="RISK_REDUCE",
            setup_type="NO_TRADE",
            size_multiplier=0.0,
        )
    )
    assert result.final_action == cr.NO_TRADE
    assert "risk_gate:RISK_REDUCE" in result.blocked_by
    assert "setup_invalid" in result.blocked_by
    assert "position_size_zero" in result.blocked_by


def test_elliott_evidence_alone_never_blocks_or_opens():
    weak = cr.resolve(_inputs(elliott_scenario="NO_VALID_COUNT", elliott_confidence=0.0))
    strong = cr.resolve(_inputs(elliott_scenario="IMPULSE_1_2_3_4_5", elliott_confidence=100.0))
    assert weak.final_action == cr.CANDIDATE_OPEN
    assert strong.final_action == cr.CANDIDATE_OPEN


# --- Faz 4: Agent Mode Permission + DQS_DEGRADED profil matrisi ---


def test_mode_filter_blocked_yields_no_trade():
    result = cr.resolve(
        _inputs(mode_filter_passed=False, mode_filter_blocked_reason="SCALP_disabled")
    )
    assert result.final_action == cr.NO_TRADE
    assert "agent_mode:SCALP_disabled" in result.blocked_by


def test_dqs_degraded_scalp_is_blocked_to_no_trade():
    result = cr.resolve(_inputs(dqs_status="DEGRADED", trade_profile="SCALP"))
    assert result.final_action == cr.NO_TRADE
    assert "dqs_degraded_scalp_blocked" in result.blocked_by


def test_dqs_degraded_intraday_is_watch_size_capped():
    result = cr.resolve(_inputs(dqs_status="DEGRADED", trade_profile="INTRADAY"))
    assert result.final_action == cr.WATCH
    assert "dqs_degraded_size_capped" in result.blocked_by


def test_dqs_degraded_swing_with_strong_confirmation_proceeds():
    result = cr.resolve(_inputs(dqs_status="DEGRADED", trade_profile="SWING"))
    assert result.final_action == cr.CANDIDATE_OPEN


def test_dqs_degraded_swing_without_confirmation_is_watch():
    result = cr.resolve(
        _inputs(dqs_status="DEGRADED", trade_profile="SWING", trigger_confirmed=False)
    )
    assert result.final_action == cr.WATCH


def test_dqs_degraded_position_is_watch():
    result = cr.resolve(_inputs(dqs_status="DEGRADED", trade_profile="POSITION"))
    assert result.final_action == cr.WATCH
    assert "dqs_degraded" in result.blocked_by


def test_dqs_degraded_without_profile_falls_back_to_generic_watch():
    result = cr.resolve(_inputs(dqs_status="DEGRADED"))
    assert result.final_action == cr.WATCH
    assert result.blocked_by == ["dqs_degraded"]
