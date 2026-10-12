"""Owner manual order safety regressions."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def manual_env(tmp_path, monkeypatch):
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper.json")
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    return paper_state


def _snapshot(score: float):
    return SimpleNamespace(
        snapshot_id="snap-test",
        prices=[SimpleNamespace(symbol="BTCUSD", price=60_000.0, verified=True)],
        quality=SimpleNamespace(score=score),
    )


def test_manual_order_cannot_bypass_risk_gate(manual_env, monkeypatch) -> None:
    from packages.paper import manual_order

    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _snapshot(40.0))
    monkeypatch.setattr(
        manual_order.price_sanity,
        "price_sane_with_ohlcv_reason",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(manual_order.ManualOrderError, match="RiskGate engelledi"):
        manual_order.place("BTCUSD", "long", 2_000.0)
    assert manual_env.load().open_positions == []


def test_manual_order_opens_when_risk_gate_allows(manual_env, monkeypatch) -> None:
    from packages.paper import manual_order

    monkeypatch.setattr(manual_order, "build_snapshot", lambda: _snapshot(90.0))
    monkeypatch.setattr(
        manual_order.price_sanity,
        "price_sane_with_ohlcv_reason",
        lambda *args, **kwargs: None,
    )

    result = manual_order.place("BTCUSD", "long", 2_000.0)
    assert result["kind"] == "market"
    assert len(manual_env.load().open_positions) == 1
