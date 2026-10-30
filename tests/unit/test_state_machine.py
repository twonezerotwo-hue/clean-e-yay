"""Karar yaşam döngüsü etiketleri — yalnız ölçülmüş gerçeklerden türetilir.

- Açık pozisyon (varlık, zaman dilimi) düzeyinde eşleşir; bir dilimdeki pozisyon
  aynı varlığın diğer dilimlerini PAPER_OPEN göstermez.
- Çelişen (sayı/sözlük) teknik teyit "hizalı" sayılmaz; yalnız True teyittir.
- Kanıt bekleyen engeller BLOCKED değil, TECHNICAL_CONFIRMED / NEWS_CONFIRMED /
  RISK_CHECKED ilerleme durumlarıdır. Hepsi offline.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.decision.cockpit import finalize_matrix_view
from packages.paper import news_setup
from packages.paper.state_machine import DecisionState, derive_decision_state


def _cell(**kw):
    base = {"symbol": "XAUUSD", "timeframe": "1h", "direction": "bullish", "blocked_by": []}
    base.update(kw)
    return base


def test_open_position_matches_symbol_and_timeframe():
    keys = {("XAUUSD", "1h")}
    assert derive_decision_state(_cell(), open_keys=keys)[0] == DecisionState.PAPER_OPEN
    assert derive_decision_state(_cell(timeframe="4h"), open_keys=keys)[0] != DecisionState.PAPER_OPEN


def test_legacy_open_symbols_still_supported():
    assert derive_decision_state(_cell(timeframe="4h"), open_symbols={"XAUUSD"})[0] == DecisionState.PAPER_OPEN


def test_conflicting_technical_value_is_not_aligned():
    # Eskiden truthy bir sayı/sözlük "Haber ve teknik kanıt hizalı" diyordu.
    cell = _cell(technical_confirmation=-0.6)
    state, _ = derive_decision_state(cell, open_keys=set())
    assert state == DecisionState.OBSERVED


def test_hard_blocker_wins_over_evidence():
    cell = _cell(blocked_by=["risk_gate:KILL_SWITCH", "technical_confirmation"], execution_state="BLOCKED")
    state, reason = derive_decision_state(cell, open_keys=set(), technical_confirmed=True, news_confirmed=True)
    assert state == DecisionState.BLOCKED
    assert "technical_confirmation" not in reason


def test_evidence_only_blockers_are_progress_states():
    cell = _cell(blocked_by=["news_confluence"], execution_state="BLOCKED", final_execution_ready=False)
    assert derive_decision_state(cell, open_keys=set(), technical_confirmed=True, news_confirmed=False)[0] == (
        DecisionState.TECHNICAL_CONFIRMED
    )
    cell = _cell(blocked_by=["technical_confirmation"], execution_state="BLOCKED", final_execution_ready=False)
    assert derive_decision_state(cell, open_keys=set(), technical_confirmed=False, news_confirmed=True)[0] == (
        DecisionState.NEWS_CONFIRMED
    )
    assert derive_decision_state(cell, open_keys=set(), technical_confirmed=False, news_confirmed=False)[0] == (
        DecisionState.RISK_CHECKED
    )


def test_ready_cell_is_paper_ready():
    cell = _cell(final_execution_ready=True, final_actionable=True)
    assert derive_decision_state(cell, open_keys=set())[0] == DecisionState.PAPER_READY


def test_non_candidate_ready_flag_is_not_paper_ready():
    # Son kapı aday olmayan hücreyi final_execution_ready=False yazar; ham bayrak etiketi yükseltmez.
    cell = _cell(final_execution_ready=False, final_actionable=False, execution_ready=True, actionable=True)
    assert derive_decision_state(cell, open_keys=set())[0] == DecisionState.OBSERVED


def _view(cells):
    return {"cells": cells, "risk_gate": {"action": "HOLD"}, "suspended": False}


def test_finalize_marks_only_the_open_timeframe(monkeypatch):
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: False)
    cells = [
        {"symbol": "XAUUSD", "timeframe": tf, "action": "hold", "paper_action": "none", "blocked_by": []}
        for tf in ("15m", "1h", "4h")
    ]
    snap = SimpleNamespace(snapshot_id="s", prices=[], technicals_by_tf={}, technicals={})
    state = SimpleNamespace(
        news_prepared_setups=[], revision=1,
        open_positions=[SimpleNamespace(symbol="XAUUSD", timeframe="1h")],
    )
    out = {c["timeframe"]: c["lifecycle_state"] for c in finalize_matrix_view(_view(cells), snap, state)["cells"]}
    assert out["1h"] == DecisionState.PAPER_OPEN
    assert out["15m"] != DecisionState.PAPER_OPEN
    assert out["4h"] != DecisionState.PAPER_OPEN


def test_finalize_names_missing_news_setup(monkeypatch):
    # Teknik teyit var, haber-teknik kurulumu yok → karar yine kapalı, etiket eksik kanıtı söyler.
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: True)
    monkeypatch.setattr(news_setup, "auto_open_mode", lambda: "require")
    monkeypatch.setattr(news_setup, "match_confluence", lambda *_a, **_k: None)
    cell = {
        "symbol": "XAGUSD", "timeframe": "1h", "action": "open_long", "execution_ready": True,
        "actionable": True, "paper_action": "open_long", "blocked_by": [],
    }
    snap = SimpleNamespace(
        snapshot_id="s",
        prices=[SimpleNamespace(symbol="XAGUSD", price=31.0, verified=True)],
        technicals_by_tf={"XAGUSD": {"1h": SimpleNamespace(
            status="OK", confirmation_signals=[SimpleNamespace(fired=True), SimpleNamespace(fired=True)],
        )}},
        technicals={},
    )
    state = SimpleNamespace(news_prepared_setups=[], revision=1, open_positions=[])
    out = finalize_matrix_view(_view([cell]), snap, state)["cells"][0]
    assert out["final_execution_ready"] is False
    assert "news_confluence" in out["blocked_by"]
    assert out["lifecycle_state"] == DecisionState.TECHNICAL_CONFIRMED
