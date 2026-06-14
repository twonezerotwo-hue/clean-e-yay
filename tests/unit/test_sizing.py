"""Phase 2c — sizing + AI-boost-strip tests.

Invariants:
- AI/opinion/persona/conviction multipliers may only reduce (clamped ≤ 1.0);
- AI never increases position size; a negative opinion reduces or blocks;
- sizing never bypasses RiskGate / DQS / KillSwitch / guards;
- an owner-approved manual-ready trade is still sized through the canonical path;
- no hardcoded boost (> 1.0) behavior remains.
"""
from __future__ import annotations

import pytest

from packages.learning import mistake_memory
from packages.paper import manual_queue, sizing
from packages.paper import state as paper_state
from packages.risk.engine import RiskInput
from packages.risk.engine import evaluate as evaluate_risk


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    return paper_state._initial_state()


def _risk(dqs: float):
    return RiskInput(
        dqs_score=dqs, equity_usd=100_000.0, peak_equity_usd=100_000.0,
        daily_pnl_usd=0.0, open_position_count=0,
    )


# 1 — AI multiplier above 1.0 is clamped to ≤ 1.0
def test_ai_multiplier_above_one_is_clamped() -> None:
    assert sizing.clamp_ai_multiplier(1.5) == 1.0
    assert sizing.clamp_ai_multiplier(2.0) == 1.0
    assert sizing.clamp_ai_multiplier(1.0001) == 1.0
    assert sizing.clamp_ai_multiplier(1.0) == 1.0
    assert sizing.clamp_ai_multiplier(None) == 1.0  # no opinion → neutral


# 2 — AI negative opinion reduces (or routes to manual via 0.0); never boosts
def test_ai_opinion_can_only_reduce() -> None:
    # boost attempt → base preserved, never increased
    assert sizing.apply_ai_opinion(1.0, 1.3) == 1.0
    assert sizing.apply_ai_opinion(1.2, 1.5) == pytest.approx(1.2)
    # negative opinion reduces
    assert sizing.apply_ai_opinion(1.0, 0.5) == pytest.approx(0.5)
    assert sizing.apply_ai_opinion(1.0, 0.0) == 0.0  # block → route to manual review


def test_compute_size_usd_caps_and_floors() -> None:
    cap = sizing._max_position_usd()
    assert sizing.compute_size_usd(1.0) == round(cap, 2)
    assert sizing.compute_size_usd(0.0) == 0.0
    assert sizing.compute_size_usd(sizing.MAX_SIZE_MULTIPLIER) == round(cap * 1.5, 2)
    assert sizing.compute_size_usd(99.0) == round(cap * 1.5, 2)  # capped, no boost above 1.5
    assert sizing.compute_size_usd(-5.0) == 0.0                  # floored, never negative


# 6 — no hardcoded boost behavior remains
def test_no_hardcoded_boost_remains() -> None:
    assert mistake_memory.SIZE_FACTOR_BOOST <= 1.0
    # Every mistake-memory size factor is restrictive-only (≤ 1.0).
    factors = [
        getattr(mistake_memory, n) for n in dir(mistake_memory) if n.startswith("SIZE_FACTOR_")
    ]
    assert factors and all(f <= 1.0 for f in factors)
    # Sizing's deterministic ceiling is the only > 1.0 constant and it is a CAP, not a
    # per-signal boost; clamp_ai_multiplier still forbids AI from reaching it.
    assert sizing.clamp_ai_multiplier(sizing.MAX_SIZE_MULTIPLIER) == 1.0


# 4 — DQS / KillSwitch cannot be bypassed by sizing
def test_dqs_below_threshold_kills_regardless_of_size(st) -> None:
    rg = evaluate_risk(_risk(dqs=40.0))
    assert rg.action == "KILL_SWITCH"  # DQS < 55 → KILL_SWITCH no matter the size


# 3 — RiskGate block still prevents opening even if sizing says valid
def test_riskgate_block_prevents_open_even_with_valid_size(st) -> None:
    entry = manual_queue.route_to_manual_ready(
        st, symbol="BTCUSD", timeframe="1d", side="long",
        size_multiplier=1.0, requested_price=60_000.0,  # perfectly valid size
    )
    res = manual_queue.approve(st, entry.id, current_price=60_000.0, risk_input=_risk(dqs=40.0))
    assert res["status"] == "blocked"
    assert res["reason"].startswith("risk_gate:")
    assert st.open_positions == []


# 5 — manual-ready approved trade is still sized through the canonical path
def test_manual_ready_approved_trade_is_safely_sized(st) -> None:
    entry = manual_queue.route_to_manual_ready(
        st, symbol="BTCUSD", timeframe="1d", side="long",
        size_multiplier=1.0, requested_price=60_000.0,
    )
    res = manual_queue.approve(st, entry.id, current_price=60_000.0, risk_input=_risk(dqs=90.0))
    assert res["status"] == "opened"
    pos = st.open_positions[0]
    assert pos.size_usd == sizing.compute_size_usd(1.0)  # sized via canonical sizing
