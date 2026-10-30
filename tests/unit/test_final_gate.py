"""Son kapı tek yerde (packages.decision.final_gate) — tick ve ekran aynı sonucu görür.

- Sıra: yürütmeye hazır → teknik veri → teknik teyit → haber etkisi → seans/conflict
  rotası; ilk düşen kapı gerekçedir (yürütülemeyen aday artık "teknik teyit yok"
  diye görünmez).
- Haber: require modunda kurulum zorunlu, conflict_reduce'ta ters kurulum boyutu küçültür.
- Ekran: tick'in yayınladığı sonuç kullanılır; owner onayına giden hücre OWNER_APPROVAL
  olur (eskiden ekranda seans kapısı ve manual_ready rotası yoktu). Hepsi offline.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.decision import final_gate, gates, tick_artifact
from packages.decision.cockpit import finalize_matrix_view
from packages.paper import news_setup
from packages.paper.state_machine import DecisionState

NOW = datetime(2026, 10, 30, 14, 0, tzinfo=UTC)


def _decision(**kw):
    base = dict(
        symbol="XAGUSD", timeframe="1h", action="open_long", actionable=True, blocked_by=[],
        expected_value=0.1, decision_id="dec-1", risk=SimpleNamespace(action="HOLD"), size_multiplier=1.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _snap(status="OK", signals=(("macd_histogram_positive", "bullish"), ("ema_stack_bullish", "bullish"))):
    sigs = [SimpleNamespace(name=n, direction=d, fired=d == "bullish") for n, d in signals]
    return SimpleNamespace(
        snapshot_id="snap-fg",
        technicals_by_tf={"XAGUSD": {"1h": SimpleNamespace(status=status, confirmation_signals=sigs)}},
        technicals={},
        prices=[SimpleNamespace(symbol="XAGUSD", price=31.0, verified=True)],
    )


def _eval(d, snap, **kw):
    args = dict(
        snap=snap, setups=[], prices={"XAGUSD": 31.0}, verified_flags={"XAGUSD": True}, now=NOW,
        regime=SimpleNamespace(label="NEUTRAL"), gate_cfg=SimpleNamespace(enabled=False), conflict_by_symbol={},
    )
    args.update(kw)
    return final_gate.evaluate(d, **args)


@pytest.fixture
def open_route(monkeypatch):
    monkeypatch.setattr(news_setup, "auto_open_mode", lambda: "conflict_reduce")
    monkeypatch.setattr(news_setup, "match_conflict", lambda *a, **k: None)
    monkeypatch.setattr(
        gates, "apply_gates",
        lambda d, **k: gates.GateDecision(route="open", effective_multiplier=1.0, session_attribution={}),
    )


def test_not_ready_candidate_is_execution_gate_even_with_stale_data(open_route):
    # Eskiden tick önce teknik veriye bakıyordu; yürütülemeyen aday yanlış gerekçe taşıyordu.
    fg = _eval(_decision(actionable=False), _snap(status="DEGRADED"))
    assert fg.route == "block" and fg.blocker == "execution_gate"


def test_exploration_cell_is_execution_gate(open_route):
    fg = _eval(_decision(blocked_by=["paper_exploration:ev_gate"]), _snap())
    assert fg.blocker == "execution_gate" and fg.detail["execution_state"] == "EXPLORATION"


def test_stale_data_then_technical_confirmation(open_route):
    assert _eval(_decision(), _snap(status="DEGRADED")).blocker == "technical_data"
    momentum_only = _snap(signals=(("macd_histogram_positive", "bullish"), ("rsi_above_50", "bullish")))
    fg = _eval(_decision(), momentum_only)
    assert fg.blocker == "technical_confirmation" and fg.technical_confirmed is False


def test_require_mode_needs_armed_setup(monkeypatch):
    monkeypatch.setattr(news_setup, "auto_open_mode", lambda: "require")
    monkeypatch.setattr(news_setup, "match_confluence", lambda *a, **k: None)
    fg = _eval(_decision(), _snap())
    assert fg.blocker == "news_confluence" and fg.news_matched is False


def test_conflict_reduces_size_and_session_routes(monkeypatch):
    monkeypatch.setattr(news_setup, "auto_open_mode", lambda: "conflict_reduce")
    monkeypatch.setattr(news_setup, "match_confluence", lambda *a, **k: None)
    monkeypatch.setattr(news_setup, "match_conflict", lambda *a, **k: {"event_id": "evt-1"})
    monkeypatch.setattr(news_setup, "_cfg", lambda: {"conflict_size_multiplier": 0.5})
    monkeypatch.setattr(
        gates, "apply_gates",
        lambda d, **k: gates.GateDecision(route="manual_ready", effective_multiplier=0.8, reason="pre_open"),
    )
    fg = _eval(_decision(), _snap())
    assert fg.route == "manual_ready" and fg.reason == "pre_open"
    assert fg.size_multiplier == pytest.approx(0.4)
    assert fg.news_effect["conflict"] == {"event_id": "evt-1"}


def test_session_block_is_last_gate(monkeypatch, open_route):
    monkeypatch.setattr(gates, "apply_gates", lambda d, **k: gates.GateDecision(route="block", effective_multiplier=0.0))
    fg = _eval(_decision(), _snap())
    assert fg.route == "block" and fg.blocker == "session_gate" and fg.technical_confirmed is True


def _view():
    cell = {
        "symbol": "XAGUSD", "timeframe": "1h", "action": "open_long", "execution_ready": True,
        "actionable": True, "paper_action": "open_long", "blocked_by": [], "decision_id": "dec-1",
    }
    return {"cells": [cell], "risk_gate": {"action": "HOLD"}, "suspended": False, "regime": "NEUTRAL"}


def test_screen_shows_tick_route_owner_approval(open_route):
    snap = _snap()
    tick_artifact.publish_final(
        snap,
        {("XAGUSD", "1h"): final_gate.FinalGate(route="manual_ready", side="long", reason="pre_open",
                                               size_multiplier=1.0, technical_confirmed=True)},
    )
    state = SimpleNamespace(news_prepared_setups=[], revision=1, open_positions=[])
    cell = finalize_matrix_view(_view(), snap, state, now=NOW)["cells"][0]
    assert cell["final_execution_ready"] is True and cell["final_actionable"] is False
    assert cell["paper_action"] == "none"
    assert cell["lifecycle_state"] == DecisionState.OWNER_APPROVAL


def test_screen_fallback_applies_session_gate(monkeypatch, open_route):
    # Tick yayını yokken ekran aynı fonksiyonu çalıştırır; seans kapısı artık ekranda da var.
    monkeypatch.setattr(gates, "apply_gates", lambda d, **k: gates.GateDecision(route="block", effective_multiplier=0.0))
    state = SimpleNamespace(news_prepared_setups=[], revision=1, open_positions=[])
    cell = finalize_matrix_view(_view(), _snap(), state, now=NOW)["cells"][0]
    assert cell["final_execution_ready"] is False
    assert "session_gate" in cell["blocked_by"]
    assert cell["lifecycle_state"] == DecisionState.BLOCKED
