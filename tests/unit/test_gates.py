"""packages/decision/gates.py — tick_worker'ın per-decision rotalama mantığının
saf-fonksiyon testleri. session_gate.evaluate_open monkeypatch'lenir (market_sessions
config'ine bağımlı olmadan); davranış orijinal inline koddakiyle birebir aynı olmalı:
session block > conflict_gate block > manual_ready (ikisinden biri) > open (çarpanlar çarpılır).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.decision import conflict_gate, conflict_resolver, gates


@dataclass(frozen=True)
class _FakeSessionGate:
    route: str
    effective_multiplier: float = 1.0
    reason_code: str | None = None

    def attribution(self) -> dict:
        return {"open_session_action": "fake", "open_session_size_multiplier": self.effective_multiplier}


def _decision(symbol="BTCUSD", timeframe="1d", risk_action="HOLD"):
    return SimpleNamespace(symbol=symbol, timeframe=timeframe, risk=SimpleNamespace(action=risk_action))


_OFF = conflict_gate.ConflictGateConfig(enabled=False)
_ON = conflict_gate.ConflictGateConfig(enabled=True)


def test_session_block_short_circuits_before_conflict_gate(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="block"))
    result = gates.apply_gates(
        _decision(), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_ON, conflict_by_symbol={"BTCUSD": {"conflict_final_action": conflict_resolver.CANDIDATE_OPEN}},
    )
    assert result.route == "block"


def test_session_open_conflict_gate_off_is_inert(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    result = gates.apply_gates(
        _decision(), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_OFF, conflict_by_symbol={"BTCUSD": {"conflict_final_action": conflict_resolver.BLOCKED}},
    )
    assert (result.route, result.effective_multiplier) == ("open", 1.0)


def test_conflict_gate_blocks_after_session_allows(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    result = gates.apply_gates(
        _decision(timeframe="1d"), side="short", now=datetime.now(UTC), regime="trend",
        gate_cfg=_ON, conflict_by_symbol={"BTCUSD": {"setup_type": "TREND_SHORT", "conflict_final_action": conflict_resolver.BLOCKED}},
    )
    # SWING (1d) HARD mode: anything but CANDIDATE_OPEN -> block
    assert result.route == "block"


def test_no_trade_conflict_uses_timeframe_profile_to_block_live_entry(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    cfg = conflict_gate.ConflictGateConfig(
        enabled=True,
        profile_modes={"INTRADAY": "HARD"},
    )
    result = gates.apply_gates(
        _decision(timeframe="1h"), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=cfg,
        conflict_by_symbol={"BTCUSD": {"setup_type": "NO_TRADE", "conflict_final_action": conflict_resolver.NO_TRADE}},
    )
    assert result.route == "block"


def test_missing_conflict_precompute_stays_fail_open(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    cfg = conflict_gate.ConflictGateConfig(
        enabled=True,
        profile_modes={"INTRADAY": "HARD"},
    )
    result = gates.apply_gates(
        _decision(timeframe="1h"), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=cfg, conflict_by_symbol={},
    )
    assert (result.route, result.effective_multiplier) == ("open", 1.0)


def test_conflict_gate_hard_manual_routes_manual_ready(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    result = gates.apply_gates(
        _decision(timeframe="1w"), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_ON, conflict_by_symbol={"BTCUSD": {"setup_type": "TREND_LONG", "conflict_final_action": conflict_resolver.CANDIDATE_OPEN}},
    )
    # POSITION (1w) HARD_MANUAL mode: CANDIDATE_OPEN -> manual_ready
    assert result.route == "manual_ready"
    assert result.reason == "conflict_gate:POSITION"


def test_session_manual_ready_wins_reason_over_conflict_gate(monkeypatch):
    monkeypatch.setattr(
        gates.session_gate, "evaluate_open",
        lambda *a, **k: _FakeSessionGate(route="manual_ready", reason_code="market_session_closing_window"),
    )
    result = gates.apply_gates(
        _decision(), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_OFF, conflict_by_symbol={},
    )
    assert result.route == "manual_ready"
    assert result.reason == "market_session_closing_window"


def test_soft_mode_multiplies_session_and_conflict_gate_factors(monkeypatch):
    monkeypatch.setattr(
        gates.session_gate, "evaluate_open",
        lambda *a, **k: _FakeSessionGate(route="open", effective_multiplier=0.8),
    )
    result = gates.apply_gates(
        _decision(timeframe="1h"), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_ON, conflict_by_symbol={"BTCUSD": {"setup_type": "TREND_LONG", "conflict_final_action": conflict_resolver.NO_TRADE}},
    )
    # INTRADAY (1h) SOFT mode: NO_TRADE -> 0.5 factor; combined = 0.8 * 0.5
    assert result.route == "open"
    assert result.effective_multiplier == pytest.approx(0.4)


def test_open_route_carries_session_attribution(monkeypatch):
    monkeypatch.setattr(gates.session_gate, "evaluate_open", lambda *a, **k: _FakeSessionGate(route="open"))
    result = gates.apply_gates(
        _decision(), side="long", now=datetime.now(UTC), regime="trend",
        gate_cfg=_OFF, conflict_by_symbol={},
    )
    assert result.session_attribution == {"open_session_action": "fake", "open_session_size_multiplier": 1.0}
