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
    agent_brief_view,
    compute_data_mode,
    compute_main_blocker,
    compute_status,
    decision_trace_view,
    next_watch_conditions,
)
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
        _snap(), SimpleNamespace(open_positions=[]),
        {"label": "LIVE", "dqs_status": "OK"}, halt_active=False,
    )
    assert brief["status"] == "ACTIONABLE"
    assert brief["can_act"] is True
    assert brief["main_blocker"]["code"] == "NONE"
    assert brief["data_mode"] == "LIVE_VERIFIED"


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


def test_cockpit_all_cells_suspended_share_global_gate():
    """Compact matrix banner şartı: suspended iken her hücre SUSPENDED."""
    r = client.get("/api/v1/decision/matrix")
    m = r.json()
    if m.get("suspended"):
        assert all(c["status"] == "SUSPENDED" for c in m["cells"])
