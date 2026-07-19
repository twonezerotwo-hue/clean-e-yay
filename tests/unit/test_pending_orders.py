"""T4 — bekleyen emir dolum-anı taze güvenlik (dış denetim P1-7).

Bekleyen emir gecikmiş owner niyetidir: emir verilirken güvenli olan koşullar
dolum anında geçerli olmayabilir. Kapsam:
- tetiklenen limit emri normal koşulda dolar (eski davranış birebir);
- aktif halt varken dolum BEKLEMEDE kalır (iptal yok) + audit yalnız bir kez;
- aynı (symbol, timeframe) açık pozisyon varken beklemede; pozisyon kapanınca dolar;
- hesap anomalisi varken beklemede.
"""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    from packages.paper import state as ps_mod
    importlib.reload(ps_mod)
    return ps_mod, tmp_path


def _with_pending(ps_mod, *, symbol="BTCUSD", tf="1d", trigger=60_000.0):
    from packages.paper.state import PendingOrder

    st = ps_mod._initial_state()
    st.pending_orders.append(
        PendingOrder(
            id="po-1", symbol=symbol, side="long", size_usd=10_000.0,
            order_type="limit", trigger_price=trigger, created_at="t", timeframe=tf,
        )
    )
    return st


def _audit_actions(tmp_path) -> list[str]:
    p = tmp_path / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(x)["action"] for x in p.read_text(encoding="utf-8").splitlines()]


def test_triggered_limit_fills_normally(env) -> None:
    ps_mod, tmp_path = env
    from packages.paper import lifecycle

    st = _with_pending(ps_mod)
    opened = lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    assert len(opened) == 1
    assert st.pending_orders == []
    assert "PENDING_FILLED" in _audit_actions(tmp_path)


def test_active_halt_holds_fill_without_cancel(env) -> None:
    ps_mod, tmp_path = env
    from packages.paper import lifecycle
    from packages.risk import halt as halt_store
    from packages.risk.engine import RiskInput

    halt_store.sync(RiskInput(
        dqs_score=90.0, equity_usd=95_000.0, peak_equity_usd=100_000.0,
        daily_pnl_usd=-5_000.0, open_position_count=0,
    ))
    assert halt_store.active_halts(), "test ön koşulu: halt persist edilmeli"

    st = _with_pending(ps_mod)
    opened = lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    assert opened == []
    assert len(st.pending_orders) == 1  # iptal YOK — beklemede
    assert st.pending_orders[0].last_held_reason == "active_halt"
    # İkinci tick: aynı sebep → yeni audit YOK (spam koruması).
    lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    actions = _audit_actions(tmp_path)
    assert actions.count("PENDING_HELD") == 1
    assert "PENDING_FILLED" not in actions


def test_duplicate_same_tf_holds_then_fills_when_cleared(env) -> None:
    ps_mod, tmp_path = env
    from packages.paper import lifecycle

    st = _with_pending(ps_mod, tf="1d")
    lifecycle.open_position(
        st, symbol="BTCUSD", side="long", entry_price=60_000.0,
        size_multiplier=1.0, timeframe="1d", open_reason="unit-test",
    )
    opened = lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    assert opened == []
    assert st.pending_orders[0].last_held_reason == "duplicate_same_tf"

    # Pozisyon kapanınca (duplicate kalkınca) aynı emir dolar; bekleme sebebi sıfırlanır.
    st.open_positions.clear()
    opened = lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    assert len(opened) == 1
    assert st.pending_orders == []
    actions = _audit_actions(tmp_path)
    assert actions.count("PENDING_HELD") == 1
    assert "PENDING_FILLED" in actions


def test_state_anomaly_holds_fill(env) -> None:
    ps_mod, _ = env
    from packages.paper import lifecycle

    st = _with_pending(ps_mod)
    st.daily_pnl_usd = st.equity_usd  # base×0.5 eşiğinin çok üstünde → anomali
    opened = lifecycle.trigger_pending_orders(st, {"BTCUSD": 59_000.0})
    assert opened == []
    assert len(st.pending_orders) == 1
    assert (st.pending_orders[0].last_held_reason or "").startswith("state_anomaly")
