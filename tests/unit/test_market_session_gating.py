"""Market-session gating into the paper open flow + attribution round-trip.

Deterministic: the exchange-calendar library is force-disabled and datetimes are
frozen, so the session gate's routing is stable regardless of wall-clock time.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from packages.learning import decision_log
from packages.paper import lifecycle, session_gate
from packages.paper import state as paper_state


@pytest.fixture(autouse=True)
def _force_fallback(monkeypatch):
    monkeypatch.setattr(
        "packages.market_sessions.calendar_provider.calendar_library_available",
        lambda: False,
    )


@pytest.fixture
def ps(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "dl.jsonl"))
    return paper_state._initial_state()


MON_MID = datetime(2026, 6, 15, 15, 0, tzinfo=UTC)       # SPY mid-session
MON_OPENING = datetime(2026, 6, 15, 13, 35, tzinfo=UTC)  # SPY opening window
SAT = datetime(2026, 6, 13, 15, 0, tzinfo=UTC)           # weekend


# ── Gate routing (deterministic) ─────────────────────────────────────────────

def test_gate_routes_open_mid_session():
    g = session_gate.evaluate_open("SPY", "long", "1d", now_utc=MON_MID)
    assert g.route == "open"
    assert g.effective_multiplier == 1.0


def test_gate_routes_manual_ready_opening_window():
    g = session_gate.evaluate_open("SPY", "long", "1d", now_utc=MON_OPENING)
    assert g.route == "manual_ready"
    assert g.reason_code == "market_session_opening_window"
    assert g.effective_multiplier == 0.5


def test_gate_routes_manual_ready_when_no_market_open():
    g = session_gate.evaluate_open("SPY", "long", "1d", now_utc=SAT)
    assert g.route == "manual_ready"
    assert g.reason_code == "market_session_no_relevant_market"


def test_crypto_routes_open_24_7():
    g = session_gate.evaluate_open("BTCUSD", "long", "1d", now_utc=SAT)
    assert g.route == "open"
    assert g.effective_multiplier == 1.0


# ── No bypass by AI/sizing: multiplier always ≤ 1.0 ──────────────────────────

def test_effective_multiplier_never_exceeds_one():
    for sym in ["SPY", "BTCUSD", "XAUUSD", "ZZZZ"]:
        for now in (MON_MID, MON_OPENING, SAT):
            g = session_gate.evaluate_open(sym, "long", "1d", now_utc=now)
            assert 0.0 <= g.effective_multiplier <= 1.0


def test_unknown_calendar_routes_manual_ready_not_open():
    # 2026-07-04: map'siz varlık (takvim bilinmiyor) artık otomatik AÇILMAZ —
    # eskiden caution/route=open idi (SPCX/TEM piyasa kapalıyken açılıyordu).
    g = session_gate.evaluate_open("ZZZZ", "long", "1d", now_utc=MON_MID)
    assert g.route == "manual_ready"
    attr = g.attribution()
    assert attr["open_session_action"] == "manual_ready"
    assert attr["open_session_size_multiplier"] == 0.5


# ── Restrictive size application ─────────────────────────────────────────────

def test_session_multiplier_reduces_opened_size(ps):
    full = lifecycle.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0, timeframe="1d"
    )
    half = lifecycle.open_position(
        ps, symbol="ETHUSD", side="long", entry_price=100.0, size_multiplier=0.5, timeframe="1d"
    )
    assert half.size_usd <= full.size_usd


# ── Attribution round-trip (open → close → decision log) ─────────────────────

def test_open_stores_session_attribution_and_logs_it(ps):
    g = session_gate.evaluate_open("BTCUSD", "long", "1d", now_utc=SAT)
    pos = lifecycle.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=g.effective_multiplier, timeframe="1d", **g.attribution(),
    )
    assert pos.open_session_action == "allow"
    assert pos.open_session_size_multiplier == 1.0
    trade = lifecycle.close_position(ps, pos, exit_price=110.0, reason="MANUAL")
    assert trade.open_session_action == "allow"
    entry = decision_log.entry_for(trade)
    assert entry["market_session"]["action"] == "allow"
    assert entry["market_session"]["size_multiplier"] == 1.0


def test_missing_session_context_does_not_crash_attribution(ps):
    pos = lifecycle.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=100.0, size_multiplier=1.0, timeframe="1d"
    )
    assert pos.open_session_action is None
    trade = lifecycle.close_position(ps, pos, exit_price=105.0, reason="MANUAL")
    entry = decision_log.entry_for(trade)  # must not raise
    assert entry["market_session"]["action"] is None
    assert entry["market_session"]["size_multiplier"] is None


# ── RiskGate / paper guards stay final: a session "allow" can't bypass them ──

def test_session_allow_does_not_bypass_price_sanity(ps):
    g = session_gate.evaluate_open("BTCUSD", "long", "1d", now_utc=SAT)
    assert g.route == "open"
    pos, decision = lifecycle.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=1e12,  # absurd → price_insane
        size_multiplier=g.effective_multiplier, timeframe="1d", **g.attribution(),
    )
    assert pos is None
    assert decision["reason"] == "price_insane"
