"""Phase 2 — deterministic paper execution simulation tests.

Acceptance:
- mark-to-market + realized fill P&L are correct and match the lifecycle path;
- SL/TP fill triggers fire in the right order, filled at the observed price;
- the formalization preserves lifecycle close behavior (close P&L == realized_pnl);
- execution_sim is pure: it makes no broker/live/network call and cannot open,
  close, resize, or mutate a trade by itself (no state/position parameter).
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from packages.paper import execution_sim


# ---------- mark-to-market + realized P&L ----------

def test_unrealized_pnl_long_and_short() -> None:
    assert execution_sim.unrealized_pnl("long", 100.0, 110.0, 1000.0) == 100.0
    assert execution_sim.unrealized_pnl("short", 100.0, 90.0, 1000.0) == 100.0
    assert execution_sim.unrealized_pnl("long", 100.0, 90.0, 1000.0) == -100.0


def test_unrealized_pnl_matches_position_property() -> None:
    from packages.paper.state import Position

    long_p = Position(
        id="x", symbol="BTCUSD", side="long", entry_price=100.0, current_price=110.0,
        size_usd=1000.0, sl=None, tp=None, opened_at="t",
    )
    short_p = dataclasses.replace(long_p, side="short", current_price=88.0)
    assert execution_sim.unrealized_pnl("long", 100.0, 110.0, 1000.0) == long_p.unrealized_pnl_usd
    assert execution_sim.unrealized_pnl("short", 100.0, 88.0, 1000.0) == short_p.unrealized_pnl_usd


def test_realized_pnl_equals_mark_at_fill_price() -> None:
    assert execution_sim.realized_pnl("long", 100.0, 120.0, 1000.0) == 200.0
    assert execution_sim.realized_pnl("short", 100.0, 120.0, 1000.0) == -200.0


# ---------- SL/TP fill triggers ----------

def test_triggered_exit_sl_and_tp() -> None:
    assert execution_sim.triggered_exit("long", 95.0, 110.0, 94.0) == "SL_HIT"
    assert execution_sim.triggered_exit("long", 95.0, 110.0, 111.0) == "TP_HIT"
    assert execution_sim.triggered_exit("long", 95.0, 110.0, 100.0) is None
    # short: SL above entry, TP below.
    assert execution_sim.triggered_exit("short", 105.0, 90.0, 106.0) == "SL_HIT"
    assert execution_sim.triggered_exit("short", 105.0, 90.0, 89.0) == "TP_HIT"


def test_triggered_exit_sl_checked_before_tp() -> None:
    # Degenerate sl==tp==price → SL takes precedence (lifecycle ordering preserved).
    assert execution_sim.triggered_exit("long", 100.0, 100.0, 100.0) == "SL_HIT"


def test_triggered_exit_none_when_levels_absent() -> None:
    assert execution_sim.triggered_exit("long", None, None, 50.0) is None


def test_simulate_exit_fill_returns_fill_or_none() -> None:
    fill = execution_sim.simulate_exit_fill(
        side="long", entry_price=100.0, sl=95.0, tp=110.0, size_usd=1000.0, price=94.0
    )
    assert fill is not None
    assert fill.reason == "SL_HIT" and fill.fill_price == 94.0
    assert fill.pnl_usd == -60.0  # (94-100)/100 * 1000
    # No trigger in the SL..TP band → None.
    assert execution_sim.simulate_exit_fill(
        side="long", entry_price=100.0, sl=95.0, tp=110.0, size_usd=1000.0, price=105.0
    ) is None


def test_fill_is_frozen_value_object() -> None:
    fill = execution_sim.Fill(reason="TP_HIT", fill_price=110.0, pnl_usd=100.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        fill.fill_price = 999.0  # type: ignore[misc]


# ---------- behavior parity with lifecycle (formalization preserved) ----------

@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    return paper_state


def test_close_position_pnl_uses_realized_pnl(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    pos = lifecycle.open_position(
        ps, symbol="ETHUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="1d",
    )
    trade = lifecycle.close_position(ps, pos, exit_price=120.0, reason="TP_HIT")
    expected = round(execution_sim.realized_pnl("long", 100.0, 120.0, pos.size_usd), 2)
    assert trade.pnl_usd == expected


def test_tick_sl_fill_matches_simulate_exit_fill(paper_env) -> None:
    from packages.paper import lifecycle

    ps = paper_env._initial_state()
    pos = lifecycle.open_position(
        ps, symbol="ETHUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, timeframe="1d",
    )
    fill_price = pos.sl - 1.0  # below SL → SL_HIT (ETHUSD: unbounded, no jump gate)
    expected_fill = execution_sim.simulate_exit_fill(
        side="long", entry_price=100.0, sl=pos.sl, tp=pos.tp,
        size_usd=pos.size_usd, price=fill_price,
    )
    closed = lifecycle.tick(ps, {"ETHUSD": fill_price})
    assert len(closed) == 1
    assert closed[0].close_reason == "SL_HIT" == expected_fill.reason
    assert closed[0].pnl_usd == round(expected_fill.pnl_usd, 2)


# ---------- purity: no broker/live, cannot open trades ----------

def test_no_live_broker_or_trade_open_calls() -> None:
    src = inspect.getsource(execution_sim)
    forbidden = (
        "import requests", "import httpx", "import socket", "urllib",
        "place_order", "open_position(", "attempt_open(", "evaluate_risk(",
        "import state", "import lifecycle", "save(", ".load(",
    )
    for token in forbidden:
        assert token not in src, f"execution_sim must not reference {token}"


def test_public_api_is_primitives_only_no_state() -> None:
    """No public function accepts a PaperState/Position/Trade — execution_sim cannot
    be handed a live object to open, close, resize, or mutate."""
    forbidden_params = {"state", "pos", "position", "positions", "trade", "paperstate"}
    for name in execution_sim.__all__:
        obj = getattr(execution_sim, name)
        if isinstance(obj, type) or not callable(obj):
            continue
        for pname in inspect.signature(obj).parameters:
            assert pname.lower() not in forbidden_params, f"{name} takes {pname!r}"
