"""UX1 — Agent Operating Cockpit ViewModel testleri.

Backend ViewModel'i tek doğruluk kaynağıdır (frontend hesap yapmaz). Bu test
seti, görev tarifindeki davranışları kilitler:

- DQS OK + RiskGate NO_POSITION_INCREASE → main_blocker RiskGate (DQS BLOCKED
  YAZMAZ, "veya" KULLANMAZ).
- Tüm hücreler aynı global gate ile SUSPENDED → compact banner şartı (suspended
  + her hücre SUSPENDED).
- Süresi dolmuş time-stop → negatif geri sayım YOK (EXPIRED + remaining 0).
- data_mode eşlemesi.

PAPER_SAFE / NO_EXECUTION: cockpit yalnızca state'i özetler; karar/emir üretmez.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routers.paper_trading import _time_stop_status
from packages.decision.cockpit import (
    _auto_open_readiness,
    agent_brief_view,
    compute_data_mode,
    compute_main_blocker,
    compute_status,
    decision_trace_view,
    finalize_matrix_view,
    next_watch_conditions,
    technical_confirmation_ready,
)
from packages.paper import news_setup
from packages.paper.state import Position

client = TestClient(app)


def _snap(score=82.0, status="OK", provider_status=None, snapshot_id="snap::test"):
    return SimpleNamespace(
        quality=SimpleNamespace(score=score, status=status),
        provider_status=provider_status or {},
        snapshot_id=snapshot_id,
    )


def _view(*, dqs="OK", risk_action="NO_POSITION_INCREASE", suspended=True, cells=None):
    return {
        "generated_at": "2026-06-13T00:00:00+00:00",
        "regime": "NEUTRAL",
        "dqs_status": dqs,
        "suspended": suspended,
        "risk_gate": {
            "action": risk_action,
            "reason": "Açık pozisyon sayısı yüksek",
            "evidence": [],
        },
        "catalysts": [],
        "cells": cells
        if cells is not None
        else [
            {
                "symbol": "BTCUSD",
                "timeframe": "1d",
                "action": "hold",
                "candidate_action": "open_long",
                "score": 62,
                "direction": "bullish",
                "confidence": 0.4,
                "size_multiplier": 0.0,
                "reason": "risk gate",
                "blocked_by": ["risk_gate:NO_POSITION_INCREASE"],
                "actionable": False,
                "status": "SUSPENDED",
                "paper_action": "none",
            }
        ],
    }


# ---------------- compute_main_blocker (tek ana engel, no "veya") ----------------

def test_main_blocker_riskgate_when_dqs_ok():
    b = compute_main_blocker(
        dqs_status="OK",
        risk_action="NO_POSITION_INCREASE",
        risk_reason="Açık pozisyon sayısı yüksek",
        halt_active=False,
        provider_down=False,
    )
    assert b["code"] == "RISK_GATE"
    assert b["label"] == "RiskGate NO_POSITION_INCREASE"
    # DQS BLOCKED YAZMAMALI + "veya" KULLANMAMALI.
    assert "DQS BLOCKED" not in b["label"]
    assert "veya" not in (b["label"] + b["detail"]).lower()


def test_main_blocker_dqs_blocked_takes_priority():
    b = compute_main_blocker(
        dqs_status="BLOCKED",
        risk_action="KILL_SWITCH",  # DQS<55 kaynaklı kill switch
        risk_reason="Veri kalitesi karar için yetersiz",
        halt_active=False,
        provider_down=False,
    )
    assert b["code"] == "DQS_BLOCKED"


def test_main_blocker_provider_down_when_blocked():
    b = compute_main_blocker(
        dqs_status="BLOCKED",
        risk_action="KILL_SWITCH",
        risk_reason="x",
        halt_active=False,
        provider_down=True,
    )
    assert b["code"] == "PROVIDER_DOWN"


def test_main_blocker_halt_when_active():
    b = compute_main_blocker(
        dqs_status="OK",
        risk_action="KILL_SWITCH",
        risk_reason="Günlük zarar limiti aşıldı",
        halt_active=True,
        provider_down=False,
    )
    assert b["code"] == "HALT"


def test_main_blocker_none_when_open():
    b = compute_main_blocker(
        dqs_status="OK",
        risk_action="HOLD",
        risk_reason="Risk kapısı açık.",
        halt_active=False,
        provider_down=False,
    )
    assert b["code"] == "NONE"


# ---------------- compute_data_mode ----------------

def test_data_mode_mapping():
    assert compute_data_mode({"label": "LIVE"}, "OK") == "LIVE_VERIFIED"
    assert compute_data_mode({"label": "INSUFFICIENT_DATA"}, "BLOCKED") == "BLOCKED"
    assert compute_data_mode({"label": "LIVE"}, "BLOCKED") == "BLOCKED"
    assert compute_data_mode({"label": "MOCK_MODE"}, "OK") == "SIMULATION"
    assert compute_data_mode({"label": "SIMULATION"}, "DEGRADED") == "PARTIAL_FALLBACK"
    assert compute_data_mode({"label": "SIMULATION"}, "OK") == "SIMULATION"


# ---------------- compute_status ----------------

def test_status_mapping():
    assert compute_status("RISK_GATE", False) == "WATCHING"
    assert compute_status("HALT", False) == "FROZEN"
    assert compute_status("DQS_BLOCKED", False) == "BLOCKED"
    assert compute_status("PROVIDER_DOWN", False) == "BLOCKED"
    assert compute_status("NONE", True) == "ACTIONABLE"
    assert compute_status("NONE", False) == "NO_ACTION"


# ---------------- agent_brief_view ----------------

def test_agent_brief_dqs_ok_riskgate_blocker():
    brief = agent_brief_view(
        _view(), _snap(), SimpleNamespace(open_positions=[]),
        {"label": "SIMULATION", "dqs_status": "OK"}, halt_active=False,
    )
    assert brief["status"] == "WATCHING"
    assert brief["main_blocker"]["code"] == "RISK_GATE"
    assert brief["can_act"] is False
    # plain-language özet DQS BLOCKED demez, "veya" kullanmaz.
    assert "DQS BLOCKED" not in brief["summary"]
    assert "veya" not in brief["summary"].lower()
    assert brief["recommended_stance"]  # boş değil


def test_agent_brief_actionable_when_open():
    cells = [
        {
            "symbol": "BTCUSD",
            "timeframe": "4h",
            "action": "open_long",
            "candidate_action": "open_long",
            "score": 71,
            "direction": "bullish",
            "actionable": True,
            "status": "ACTIONABLE",
            "blocked_by": [],
            "paper_action": "open_long",
        }
    ]
    brief = agent_brief_view(
        _view(risk_action="HOLD", suspended=False, cells=cells),
        SimpleNamespace(
            **_snap().__dict__,
            technicals_by_tf={"BTCUSD": {"4h": SimpleNamespace(status="OK")}},
            technicals={},
        ),
        SimpleNamespace(open_positions=[]),
        {"label": "LIVE", "dqs_status": "OK"}, halt_active=False,
    )
    assert brief["status"] == "ACTIONABLE"
    assert brief["can_act"] is True
    assert brief["main_blocker"]["code"] == "NONE"
    assert brief["data_mode"] == "LIVE_VERIFIED"


def test_auto_open_readiness_exposes_final_news_gate(monkeypatch):
    """Matrix READY must not be reported as an opened paper action."""
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: True)
    monkeypatch.setattr(news_setup, "match_confluence", lambda *_args, **_kwargs: None)
    cells = [{
        "symbol": "XAGUSD",
        "timeframe": "15m",
        "action": "open_short",
        "execution_ready": True,
        "actionable": True,
    }]
    snap = SimpleNamespace(
        prices=[SimpleNamespace(symbol="XAGUSD", price=31.2, verified=True)],
        technicals_by_tf={"XAGUSD": {"15m": SimpleNamespace(status="OK")}},
        technicals={},
    )
    state = SimpleNamespace(news_prepared_setups=[])
    readiness = _auto_open_readiness(cells, snap, state)
    assert readiness["candidate_count"] == 1
    assert readiness["ready_count"] == 0
    assert readiness["blocked_count"] == 1
    assert readiness["blockers"][0]["code"] == "news_confluence"


def test_finalize_matrix_view_removes_pre_gate_paper_action(monkeypatch):
    """All read surfaces must expose final paper intent, not a pre-gate intent."""
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: True)
    monkeypatch.setattr(news_setup, "match_confluence", lambda *_args, **_kwargs: None)
    view = _view(
        risk_action="HOLD",
        suspended=False,
        cells=[{
            "symbol": "XAGUSD",
            "timeframe": "15m",
            "action": "open_short",
            "execution_ready": True,
            "actionable": True,
            "paper_action": "open_short",
            "blocked_by": [],
        }],
    )
    snap = SimpleNamespace(
        snapshot_id="snap-1",
        prices=[SimpleNamespace(symbol="XAGUSD", price=31.2, verified=True)],
        technicals_by_tf={"XAGUSD": {"15m": SimpleNamespace(status="OK")}},
        technicals={},
    )
    state = SimpleNamespace(news_prepared_setups=[], revision=4)

    result = finalize_matrix_view(view, snap, state)
    cell = result["cells"][0]
    assert cell["paper_action_intent"] == "open_short"
    assert cell["paper_action"] == "none"
    assert cell["final_execution_ready"] is False
    assert "news_confluence" in cell["blocked_by"]
    assert result["paper_actions"] == []
    assert result["pending_paper_actions"][0]["paper_action"] == "open_short"


def test_finalize_matrix_view_blocks_degraded_technical_cell(monkeypatch):
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: False)
    view = _view(
        risk_action="HOLD",
        suspended=False,
        cells=[{
            "symbol": "DODO",
            "timeframe": "15m",
            "action": "open_long",
            "execution_ready": True,
            "actionable": True,
            "paper_action": "open_long",
            "blocked_by": [],
        }],
    )
    snap = SimpleNamespace(
        snapshot_id="snap-2",
        prices=[SimpleNamespace(symbol="DODO", price=1.0, verified=True)],
        technicals_by_tf={"DODO": {"15m": SimpleNamespace(status="DEGRADED")}},
        technicals={},
    )
    state = SimpleNamespace(news_prepared_setups=[], revision=5)

    cell = finalize_matrix_view(view, snap, state)["cells"][0]
    assert cell["paper_action"] == "none"
    assert cell["final_execution_ready"] is False
    assert "technical_data" in cell["blocked_by"]


def test_technical_confirmation_requires_same_side_indicators():
    snap = SimpleNamespace(
        technicals_by_tf={
            "XAGUSD": {
                "1h": SimpleNamespace(
                    status="OK",
                    confirmation_signals=[
                        SimpleNamespace(fired=True),
                        SimpleNamespace(fired=False),
                        SimpleNamespace(fired=True),
                    ],
                )
            }
        },
        technicals={},
    )
    assert technical_confirmation_ready(snap, "XAGUSD", "1h", "long")[0]
    assert not technical_confirmation_ready(snap, "XAGUSD", "1h", "short")[0]


def test_4h_requires_three_same_side_confirmations(monkeypatch):
    """The calibrated 4h path is stricter; other TFs keep the legacy default."""
    snap = SimpleNamespace(
        technicals_by_tf={
            "XAGUSD": {
                "4h": SimpleNamespace(
                    status="OK",
                    confirmation_signals=[
                        SimpleNamespace(fired=True),
                        SimpleNamespace(fired=True),
                        SimpleNamespace(fired=False),
                    ],
                ),
                "1h": SimpleNamespace(
                    status="OK",
                    confirmation_signals=[
                        SimpleNamespace(fired=True),
                        SimpleNamespace(fired=True),
                    ],
                ),
            }
        },
        technicals={},
    )
    assert not technical_confirmation_ready(snap, "XAGUSD", "4h", "long")[0]
    assert technical_confirmation_ready(snap, "XAGUSD", "1h", "long")[0]


def test_finalize_matrix_view_blocks_unconfirmed_direction(monkeypatch):
    monkeypatch.setattr(news_setup, "require_confluence_for_auto_open", lambda: False)
    view = _view(
        risk_action="HOLD",
        suspended=False,
        cells=[{
            "symbol": "XAGUSD",
            "timeframe": "1h",
            "action": "open_long",
            "execution_ready": True,
            "actionable": True,
            "paper_action": "open_long",
            "blocked_by": [],
        }],
    )
    snap = SimpleNamespace(
        snapshot_id="snap-confirmation",
        technicals_by_tf={
            "XAGUSD": {
                "1h": SimpleNamespace(
                    status="OK",
                    confirmation_signals=[SimpleNamespace(fired=True)],
                )
            }
        },
        technicals={},
        prices=[],
    )
    state = SimpleNamespace(news_prepared_setups=[], revision=1)
    cell = finalize_matrix_view(view, snap, state)["cells"][0]
    assert cell["paper_action"] == "none"
    assert cell["final_execution_ready"] is False
    assert "technical_confirmation" in cell["blocked_by"]


# ---------------- next_watch_conditions ----------------

def test_watch_conditions_expired_time_stop_and_position_count():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    positions = [
        SimpleNamespace(symbol=f"S{i}", valid_until=past) for i in range(6)
    ]
    conds = next_watch_conditions(_view(), _snap(), positions)
    keys = {c["key"] for c in conds}
    assert "position_count" in keys
    assert "time_stop_resolved" in keys
    assert "risk_gate_clear" in keys


# ---------------- decision_trace_view ----------------

def test_decision_trace_shape():
    trace = decision_trace_view(_view(), _snap())
    assert trace["candidate_decisions"]
    assert trace["final_decisions"]
    assert "risk_gate:NO_POSITION_INCREASE" in trace["blocked_by"]
    assert "RiskGate" in trace["restrictive_gates"]
    assert any(r.startswith("snapshot:") for r in trace["evidence_refs"])


# ---------------- time-stop serileştirme (negatif geri sayım YOK) ----------------

def test_time_stop_expired_no_negative():
    now = datetime.now(UTC)
    past = (now - timedelta(hours=2)).isoformat()
    p = Position(
        id="p1", symbol="BTCUSD", side="long", entry_price=1.0,
        current_price=1.0, size_usd=10.0, sl=None, tp=None,
        opened_at=now.isoformat(), valid_until=past,
    )
    status, remaining = _time_stop_status(p, now)
    assert status == "EXPIRED"
    assert remaining == 0  # asla negatif


def test_time_stop_active_positive():
    now = datetime.now(UTC)
    future = (now + timedelta(hours=2)).isoformat()
    p = Position(
        id="p2", symbol="ETHUSD", side="long", entry_price=1.0,
        current_price=1.0, size_usd=10.0, sl=None, tp=None,
        opened_at=now.isoformat(), valid_until=future,
    )
    status, remaining = _time_stop_status(p, now)
    assert status == "ACTIVE"
    assert remaining > 0


def test_time_stop_none_when_no_valid_until():
    now = datetime.now(UTC)
    p = Position(
        id="p3", symbol="XAUUSD", side="long", entry_price=1.0,
        current_price=1.0, size_usd=10.0, sl=None, tp=None,
        opened_at=now.isoformat(), valid_until=None,
    )
    status, remaining = _time_stop_status(p, now)
    assert status == "NONE"
    assert remaining is None


# ---------------- endpoint ----------------

def test_cockpit_brief_endpoint():
    r = client.get("/api/v1/cockpit/brief")
    assert r.status_code == 200
    body = r.json()
    assert "agent_brief" in body and "decision_trace" in body
    ab = body["agent_brief"]
    assert ab["status"] in (
        "ACTIONABLE", "NO_ACTION", "WATCHING", "FROZEN", "BLOCKED"
    )
    assert ab["main_blocker"]["code"] in (
        "DQS_BLOCKED", "HALT", "PROVIDER_DOWN", "RISK_GATE", "NONE"
    )
    # tek ana engel — "veya" yok.
    assert "veya" not in ab["main_blocker"]["label"].lower()
    # Layer-0 yönetici metni aynı cockpit snapshot'ı ve paper revision'ı ile
    # üretilir; ayrı /agent/briefing cache'ine düşmemelidir.
    assert body.get("snapshot_id")
    assert body.get("paper_state_revision") is not None
    assert body.get("brief_id")
    assert body.get("executive", {}).get("headline")
    assert body["decision_matrix"]["snapshot_id"] == body["snapshot_id"]
    assert body["decision_matrix"]["paper_state_revision"] == body["paper_state_revision"]
    assert body["paper_state"]["revision"] == body["paper_state_revision"]
    assert isinstance(body.get("prices"), list)
    assert isinstance(body.get("headlines"), list)


def test_cockpit_state_is_the_same_canonical_envelope():
    state = client.get("/api/v1/cockpit/state")
    brief = client.get("/api/v1/cockpit/brief")
    assert state.status_code == 200
    assert brief.status_code == 200
    state_body = state.json()
    brief_body = brief.json()
    ids = state_body["canonical_ids"]
    assert ids["snapshot_id"] == state_body["snapshot_id"]
    assert ids["brief_id"] == state_body["brief_id"]
    assert ids["paper_state_revision"] == state_body["paper_state_revision"]
    assert state_body["snapshot_id"] == brief_body["snapshot_id"]
    assert state_body["brief_id"] == brief_body["brief_id"]


def test_legacy_agent_briefing_reuses_cockpit_envelope():
    cockpit = client.get("/api/v1/cockpit/brief")
    legacy = client.get("/api/v1/agent/briefing")
    assert cockpit.status_code == legacy.status_code == 200
    assert legacy.json()["snapshot_id"] == cockpit.json()["snapshot_id"]
    assert legacy.json()["paper_state_revision"] == cockpit.json()["paper_state_revision"]
    assert legacy.json()["brief_id"] == cockpit.json()["brief_id"]


def test_cockpit_all_cells_suspended_share_global_gate():
    """Compact matrix banner şartı: suspended iken her hücre SUSPENDED."""
    r = client.get("/api/v1/decision/matrix")
    m = r.json()
    if m.get("suspended"):
        assert all(c["status"] == "SUSPENDED" for c in m["cells"])
