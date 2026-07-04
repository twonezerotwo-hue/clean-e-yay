"""risk_gates.max_open_positions — 2026-07-04: hardcoded 6 → owner-tunable config.

Davranış default'ta bayt-aynı (limit 6); config'ten değiştirilebilir. Limit
yalnızca kısıtlar (NO_POSITION_INCREASE) — hiçbir gate'i gevşetemez.
"""
from __future__ import annotations

import pytest

from packages.risk import engine


@pytest.fixture(autouse=True)
def _isolated_halt(tmp_path, monkeypatch):
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))


def _inp(count: int) -> engine.RiskInput:
    return engine.RiskInput(
        dqs_score=80.0,
        equity_usd=100_000.0,
        peak_equity_usd=100_000.0,
        daily_pnl_usd=0.0,
        open_position_count=count,
    )


def _th(max_open: int | None = None) -> dict:
    gates = {
        "max_daily_loss_pct": 0.02,
        "max_drawdown_pct": 0.08,
    }
    if max_open is not None:
        gates["max_open_positions"] = max_open
    return {"risk_gates": gates}


def test_default_limit_is_six(monkeypatch):
    # Anahtar YOKSA default 6 — eski hardcoded davranış birebir.
    monkeypatch.setattr(engine, "load_thresholds", lambda: _th())
    assert engine.evaluate(_inp(5)).action == "HOLD"
    d = engine.evaluate(_inp(6))
    assert d.action == "NO_POSITION_INCREASE"
    assert any("limit 6" in e for e in d.evidence)


def test_config_can_raise_limit(monkeypatch):
    monkeypatch.setattr(engine, "load_thresholds", lambda: _th(8))
    assert engine.evaluate(_inp(7)).action == "HOLD"
    assert engine.evaluate(_inp(8)).action == "NO_POSITION_INCREASE"


def test_config_can_tighten_limit(monkeypatch):
    monkeypatch.setattr(engine, "load_thresholds", lambda: _th(3))
    assert engine.evaluate(_inp(3)).action == "NO_POSITION_INCREASE"


def test_limit_does_not_relax_higher_priority_gates(monkeypatch):
    # Limit yükseltmek DQS KILL_SWITCH'i asla gevşetemez.
    monkeypatch.setattr(engine, "load_thresholds", lambda: _th(100))
    low_dqs = engine.RiskInput(
        dqs_score=40.0,
        equity_usd=100_000.0,
        peak_equity_usd=100_000.0,
        daily_pnl_usd=0.0,
        open_position_count=0,
    )
    assert engine.evaluate(low_dqs).action == "KILL_SWITCH"


def test_live_yaml_has_the_key():
    # Canlı config anahtarı taşımalı (default'a sessiz düşüş yok).
    from packages.data.registry.loader import load_thresholds

    assert int(load_thresholds()["risk_gates"]["max_open_positions"]) == 6
