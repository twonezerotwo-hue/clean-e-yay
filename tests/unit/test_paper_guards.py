"""Phase 2 — price sanity + state anomaly guard tests (ported from e-yay-codex).

Acceptance:
- cross-pair contamination (BTC getting silver/gold/oil-like price) is rejected;
- a price jump above threshold is rejected;
- contaminated entry does not OPEN a position;
- a contaminated tick does not CLOSE/manage a position on garbage;
- absurd accounting state blocks NEW opens but still allows risk-reducing closes.
"""
from __future__ import annotations

import pytest

from packages.data.guards import price_sanity
from packages.paper.guards import state_anomaly

# Dilim-0 — attempt_open OHLCV referans kapısından geçer (conftest seed).
pytestmark = pytest.mark.usefixtures("seed_ohlcv_reference")

# ---------- price sanity (unit) ----------

def test_absolute_bounds_reject_and_accept() -> None:
    assert price_sanity.is_price_sane("BTCUSD", 60_000.0) is True
    assert price_sanity.is_price_sane("BTCUSD", 100.0) is False          # below 20k
    assert price_sanity.is_price_sane("BTCUSD", 1_000_000.0) is False    # above 500k


def test_cross_pair_contamination_rejected() -> None:
    # BTC slot receiving silver/gold/oil-like prices → out of BTC bounds.
    for contaminated in (30.0, 2_000.0, 85.0, 716.0, 7_405.0):
        assert price_sanity.is_price_sane("BTCUSD", contaminated) is False


def test_jump_guard_rejects_absurd_move() -> None:
    # Plausible-by-bounds but impossible vs previous tick (64000 → 7405 = 88% drop).
    assert price_sanity.is_price_sane("BTCUSD", 25_000.0, previous_price=64_000.0) is False
    # Small move is fine.
    assert price_sanity.is_price_sane("BTCUSD", 64_500.0, previous_price=64_000.0) is True


def test_reference_price_guard_rejects_same_symbol_scale_mismatch() -> None:
    # XAGUSD 27.95 is within absolute bounds, but not sane vs a 57.48 OHLCV close.
    reason = price_sanity.price_sane_reason(
        "XAGUSD", 27.95, reference_price=57.48, reference_label="ohlcv:15m"
    )
    assert reason is not None and "ohlcv:15m_jump" in reason
    assert price_sanity.is_price_sane("XAGUSD", 57.50, reference_price=57.48) is True


def test_tick_price_usable_rejects_in_bounds_scale_jump() -> None:
    assert price_sanity.tick_price_usable("XAGUSD", 27.95, last_price=57.48) is False
    assert price_sanity.tick_price_usable("XAGUSD", 57.50, last_price=57.48) is True


def test_unbounded_symbol_positivity_only() -> None:
    assert price_sanity.is_price_sane("ETHUSD", 3_000.0) is True
    assert price_sanity.is_price_sane("ETHUSD", 0.0) is False
    assert price_sanity.is_price_sane("ETHUSD", -5.0) is False


def test_reason_is_machine_readable() -> None:
    assert price_sanity.price_sane_reason("BTCUSD", 60_000.0) is None
    assert "out_of_bounds" in (price_sanity.price_sane_reason("BTCUSD", 100.0) or "")
    assert "jump" in (
        price_sanity.price_sane_reason("BTCUSD", 25_000.0, previous_price=64_000.0) or ""
    )


# ---------- state anomaly (unit) ----------

def test_state_anomaly_detects_inflated_equity_and_pnl() -> None:
    # base = initial_equity_usd (100_000); multiplier 3.0, daily fraction 0.5.
    a = state_anomaly.detect(realized_pnl_usd=400_000.0, equity_usd=100_000.0, daily_pnl_usd=0.0)
    assert a.detected is True and a.reasons
    a2 = state_anomaly.detect(realized_pnl_usd=0.0, equity_usd=500_000.0, daily_pnl_usd=0.0)
    assert a2.detected is True
    a3 = state_anomaly.detect(realized_pnl_usd=0.0, equity_usd=100_000.0, daily_pnl_usd=60_000.0)
    assert a3.detected is True


def test_state_anomaly_clean_state_ok() -> None:
    a = state_anomaly.detect(realized_pnl_usd=1_200.0, equity_usd=101_200.0, daily_pnl_usd=300.0)
    assert a.detected is False and a.reasons == []


# ---------- lifecycle integration ----------

@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "paper_audit.jsonl"))
    return paper_state


def test_attempt_open_rejects_contaminated_entry(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=30.0,  # silver-like contamination
        size_multiplier=1.0, timeframe="1d",
    )
    assert pos is None
    assert decision["reason"] == "price_insane"
    assert ps.open_positions == []


def test_contaminated_tick_does_not_close_position(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    lifecycle.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=60_000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    closed = lifecycle.tick(ps, {"BTCUSD": 7_405.0})  # cross-pair contamination
    assert closed == []                                # not closed on garbage
    assert len(ps.open_positions) == 1
    assert ps.open_positions[0].current_price == 60_000.0  # price not updated


def test_state_anomaly_blocks_new_open(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    ps.realized_pnl_usd = 400_000.0  # absurd vs base 100k → anomaly
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60_000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    assert pos is None
    assert decision["reason"] == "state_anomaly"
    assert decision["anomaly_reasons"]


def test_state_anomaly_does_not_block_close(paper_env) -> None:
    """Risk-reducing close must stay possible even when state is anomalous."""
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    lifecycle.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=60_000.0,
        size_multiplier=1.0, timeframe="1d",
    )
    ps.equity_usd = 1_000_000.0  # make state anomalous AFTER opening
    assert state_anomaly.detect_state(ps).detected is True
    closed = lifecycle.flatten_all(ps, {"BTCUSD": 60_300.0}, reason="KILL_SWITCH_EXIT")
    assert len(closed) == 1                       # close still works
    assert ps.open_positions == []
