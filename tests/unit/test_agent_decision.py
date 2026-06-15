"""AgentDecision (T2) tests + architecture guards.

Constructs ConsensusSnapshot inputs directly (deterministic). Covers the spec
guard test_upper_tf_only_scales_down plus RiskGate dominance, conditional
countertrend, 1w-no-entry, and risk_gate_required always true.
"""
from __future__ import annotations

from packages.data.types import ConsensusSnapshot
from packages.decision import agent_decision as ad


def _cs(**kw) -> ConsensusSnapshot:
    base = dict(
        asset="BTCUSD",
        per_timeframe_bias={"d1": "BULLISH", "h1": "BULLISH"},
        alignment_status="ALIGNED",
        alignment_score=100.0,
        agreement_score=100.0,
        direction_score=70.0,
        strength_score=70.0,
        is_countertrend=False,
        confirmed_count=2,
    )
    base.update(kw)
    return ConsensusSnapshot(**base)


# ── RiskGate is final (TF-agnostic) ───────────────────────────────────────────

def test_kill_switch_dominates_bullish_consensus():
    d = ad.decide("BTCUSD", _cs(), risk_action="KILL_SWITCH")
    assert d.action == "KILL_SWITCH"
    assert d.size_multiplier == 0.0
    assert d.risk_gate_required is True


def test_risk_reduce_and_no_position_increase_restrictive():
    assert ad.decide("BTCUSD", _cs(), risk_action="RISK_REDUCE").action == "RISK_REDUCE"
    assert ad.decide("BTCUSD", _cs(), risk_action="NO_POSITION_INCREASE").action == "NO_TRADE"


# ── Evidence → action ─────────────────────────────────────────────────────────

def test_insufficient_consensus_is_no_trade():
    d = ad.decide("BTCUSD", _cs(direction_score=None))
    assert d.action == "NO_TRADE"
    assert d.entry_timeframe is None


def test_neutral_lean_is_no_trade():
    d = ad.decide("BTCUSD", _cs(direction_score=50.0))
    assert d.action == "NO_TRADE"


def test_conflicted_is_watch():
    d = ad.decide("BTCUSD", _cs(alignment_status="CONFLICTED", direction_score=58.0))
    assert d.action == "WATCH"


def test_aligned_confirmed_is_scout_allowed():
    d = ad.decide("BTCUSD", _cs())  # entry = lowest executable bullish = 1h (base 0.5)
    assert d.action == "SCOUT_ALLOWED"
    assert d.entry_timeframe == "1h"
    assert d.size_multiplier == 0.5      # 1h base; never boosted by agreeing upper TFs
    assert d.manual_ready_required is False
    assert d.confidence == 1.0


def test_aligned_pending_requires_confirmation():
    d = ad.decide("BTCUSD", _cs(confirmed_count=0))
    assert d.action == "CONFIRMATION_REQUIRED"
    assert any(r.startswith("trigger_confirmation") for r in d.required_confirmations)


def test_1w_only_directional_is_watch_no_entry():
    d = ad.decide(
        "BTCUSD",
        _cs(per_timeframe_bias={"w1": "BULLISH", "d1": "NEUTRAL", "h4": "NEUTRAL", "h1": "NEUTRAL"}),
    )
    assert d.action == "WATCH"
    assert d.entry_timeframe is None     # 1w yields bias only, never an entry


# ── Conditional countertrend (never auto full entry) ──────────────────────────

def test_countertrend_confirmed_is_reduced_scout_manual_ready():
    d = ad.decide("BTCUSD", _cs(is_countertrend=True, confirmed_count=1))
    assert d.action == "SCOUT_ALLOWED"
    assert d.manual_ready_required is True
    assert d.size_multiplier < 0.5       # 1h base 0.5 × countertrend cap 0.5 = 0.25
    assert d.size_multiplier == 0.25


def test_countertrend_unconfirmed_requires_confirmation():
    d = ad.decide("BTCUSD", _cs(is_countertrend=True, confirmed_count=0))
    assert d.action == "CONFIRMATION_REQUIRED"
    assert d.manual_ready_required is True


# ── Guard: upper TF only scales DOWN, never up; size ≤ 1.0 ────────────────────

def test_upper_tf_only_scales_down():
    # Entry on 4h (base multiplier 1.0) so the cap-at-1.0 is visible.
    bias = {"d1": "BULLISH", "h4": "BULLISH"}
    aligned = ad.decide("BTCUSD", _cs(per_timeframe_bias=bias))
    counter = ad.decide("BTCUSD", _cs(per_timeframe_bias=bias, is_countertrend=True, confirmed_count=1))

    assert aligned.entry_timeframe == "4h" and counter.entry_timeframe == "4h"
    # Agreeing upper TF does NOT boost the entry above its own base cap.
    assert aligned.size_multiplier == 1.0
    assert aligned.size_multiplier <= 1.0
    # Disagreeing (countertrend) upper TF only scales DOWN.
    assert counter.size_multiplier < aligned.size_multiplier
    assert counter.size_multiplier == 0.5
    # No path ever exceeds 1.0.
    for d in (aligned, counter):
        assert d.size_multiplier <= 1.0


def test_risk_gate_required_always_true():
    cases = [
        ad.decide("BTCUSD", _cs()),
        ad.decide("BTCUSD", _cs(direction_score=None)),
        ad.decide("BTCUSD", _cs(alignment_status="CONFLICTED")),
        ad.decide("BTCUSD", _cs(is_countertrend=True, confirmed_count=0)),
        ad.decide("BTCUSD", _cs(), risk_action="KILL_SWITCH"),
    ]
    assert all(d.risk_gate_required is True for d in cases)
