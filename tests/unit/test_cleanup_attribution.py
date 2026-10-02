"""H5 / H6 / K1 — açılış atfı (risk, DQS, kapı listesi, keşif) kapanışa kadar taşınır."""
from __future__ import annotations

import pytest

from packages.learning import decision_log, outcomes
from packages.paper import lifecycle
from packages.paper.state import PaperState

pytestmark = pytest.mark.usefixtures("seed_ohlcv_reference")  # BTCUSD@60000


def _open(state: PaperState, blocked_by: list[str] | None):
    pos, decision = lifecycle.attempt_open(
        state,
        symbol="BTCUSD",
        side="long",
        entry_price=60_000.0,
        size_multiplier=0.35,
        timeframe="1d",
        open_reason="test",
        snapshot_id="snap::t",
        fingerprint="BTCUSD|v2|1d|NEUTRAL|bullish|S55|X|touche",
        data_verified=True,
        predicted_confidence=0.22,
        raw_confidence=0.2,
        confidence_source="fitted",
        open_dqs=88.0,
        open_risk_action="HOLD",
        open_blocked_by=blocked_by,
    )
    assert pos is not None, decision
    return pos


def test_is_exploration_detects_policy_tag() -> None:
    assert lifecycle.is_exploration(["paper_exploration:ev_gate"])
    assert not lifecycle.is_exploration(["kelly_cap", "sizing_layers"])
    assert not lifecycle.is_exploration(None)


def test_exploration_and_gates_survive_to_decision_log_and_outcome() -> None:
    state = PaperState(equity_usd=100_000.0, peak_equity_usd=100_000.0)
    pos = _open(state, ["kelly_cap", "paper_exploration:confidence_floor"])
    assert pos.exploration is True
    assert pos.open_dqs == 88.0 and pos.open_risk_action == "HOLD"

    trade = lifecycle.close_position(state, pos, exit_price=60_500.0, reason="TP_HIT")
    assert trade.exploration is True
    assert trade.open_blocked_by == ["kelly_cap", "paper_exploration:confidence_floor"]

    entry = decision_log.entry_for(trade)
    assert entry["diagnostics"] == []  # risk + DQS artık eksik değil
    assert entry["opening_signal"]["exploration"] is True
    assert entry["opening_signal"]["blocked_by"] == trade.open_blocked_by

    from_trade = outcomes.build_outcome(trade)
    from_log = outcomes.build_outcome_from_log_entry(entry)
    for o in (from_trade, from_log):
        assert o.exploration is True
        assert "paper_exploration:confidence_floor" in o.blocked_by


def test_normal_open_is_not_exploration() -> None:
    state = PaperState(equity_usd=100_000.0, peak_equity_usd=100_000.0)
    pos = _open(state, ["kelly_cap"])
    assert pos.exploration is False


def test_legacy_log_entry_defaults() -> None:
    entry = {"opening_signal": {"fingerprint": None}, "outcome": {}, "exit": {}}
    o = outcomes.build_outcome_from_log_entry(entry)
    assert o.exploration is False and o.blocked_by == []


# ── K1 kohort politikası: keşif yalnız kalibrasyona girer ──────────────────────

def _outcome(exploration: bool):
    entry = {
        "opening_signal": {
            "fingerprint": "BTCUSD|v2|1d|NEUTRAL|bullish|S55|X|touche",
            "data_verified": True,
            "raw_confidence": 0.2,
            "exploration": exploration,
        },
        "outcome": {"entry_price": 100.0, "exit_price": 101.0, "pnl_usd": 1.0},
        "exit": {"reason": "TP_HIT"},
        "timeframe": "1d",
        "side": "long",
    }
    return outcomes.build_outcome_from_log_entry(entry)


def test_learning_grade_excludes_exploration_by_default() -> None:
    normal, expl = _outcome(False), _outcome(True)
    assert outcomes.learning_grade([normal, expl]) == [normal]
    assert outcomes.learning_grade([normal, expl], include_exploration=True) == [normal, expl]


def test_cohort_classifies_exploration_separately() -> None:
    from packages.learning import cohorts

    assert cohorts.classify(_outcome(True)) == cohorts.EXPLORATION
    assert cohorts.classify(_outcome(False)) == cohorts.AUTO
    summary = cohorts.cohort_summary([_outcome(True), _outcome(False)])
    assert summary["exploration"]["trades"] == 1 and summary["auto"]["trades"] == 1
