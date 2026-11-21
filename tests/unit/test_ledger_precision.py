"""D4 (22 Kasım 2026) — defter fiyatları yuvarlanmaz; R paydası açılıştaki risk."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


@pytest.fixture
def ps_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state
    importlib.reload(state)
    return state


def _open(lifecycle, st, symbol, entry):
    return lifecycle.open_position(
        st, symbol=symbol, side="long", entry_price=entry, size_multiplier=0.0,
        manual=True, size_usd_override=1000.0, timeframe="1d",
    )


def test_low_price_exit_is_not_rounded(ps_mod) -> None:
    from packages.paper import lifecycle
    st = ps_mod._initial_state()
    pos = _open(lifecycle, st, "DODO", 0.04262235)
    trade = lifecycle.close_position(st, pos, exit_price=0.04301234, reason="MANUAL")
    assert trade.exit_price == 0.04301234


def test_r_denominator_is_the_risk_at_open(ps_mod) -> None:
    from packages.paper import lifecycle
    st = ps_mod._initial_state()
    pos = _open(lifecycle, st, "BTCUSD", 100.0)
    risk_at_open = round(abs(100.0 - pos.sl) / 100.0, 6)
    assert pos.open_risk_pct == risk_at_open
    pos.sl = 100.0  # owner stopu başabaşa çekti
    trade = lifecycle.close_position(st, pos, exit_price=103.0, reason="MANUAL")
    assert trade.open_risk_pct == risk_at_open  # eski kod: 0.0 (R tanımsız)


def test_scale_in_average_entry_is_not_rounded(ps_mod, monkeypatch) -> None:
    from packages.paper import lifecycle, position_ops
    with ps_mod.transaction("test") as st:
        pos = _open(lifecycle, st, "DODO", 0.04262235)
    snap = SimpleNamespace(quality=SimpleNamespace(score=90.0), catalysts=[])
    monkeypatch.setattr(position_ops, "_market_price", lambda symbol: (0.04301234, snap))
    out = position_ops.scale_in(pos.id, 1000.0)
    expected = 2000.0 / (1000.0 / 0.04262235 + 1000.0 / 0.04301234)
    assert out["avg_entry"] == pytest.approx(expected, rel=1e-12)
    assert round(expected, 4) != pytest.approx(expected, rel=1e-6)  # eski yuvarlama farkı görünür
