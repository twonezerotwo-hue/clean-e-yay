"""S serisi (2026-07-04) — hız + acil düzeltme regresyon testleri.

S1-2: shadow log tail-read + rotasyon (221MB tam-dosya okuma bitti; rotasyon
      sınırında bile aynı kayıt kümesi döner — davranış-nötr).
S1-3: agent_pipeline TF-sonuç memosu (tick başına çifte ağır hesap tek sefer;
      farklı bar serisi → yeniden hesap, explicit `now` → memo devre dışı).
S1-4: tick worker degraded sınıflandırması (opsiyonel sağlayıcı arızası tek
      başına worker'ı DEGRADED yapmaz; sebepler yine listelenir).
S2-1: RiskEngine MTM drawdown girdisi (flag KAPALI → bayt-aynı; açık →
      yalnız SIKILAŞTIRIR, MTM kârı gate'i gevşetemez).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from packages.decision import agent_pipeline
from packages.risk.engine import RiskInput, evaluate

# ── S1-3: agent_pipeline TF-sonuç memosu ─────────────────────────────────────

def _bars(n, base_close=100.0):
    return [
        SimpleNamespace(
            ts=datetime(2026, 7, 1, i % 24, tzinfo=UTC), close=base_close + i
        )
        for i in range(n)
    ]


def test_tf_memo_computes_once_for_same_bars(monkeypatch):
    agent_pipeline._tf_memo.clear()
    calls = {"n": 0}

    def fake_build(symbol, tf, bars, now=None):
        calls["n"] += 1
        return SimpleNamespace(symbol=symbol, tf=tf, n=len(bars))

    monkeypatch.setattr(agent_pipeline, "build_timeframe_result", fake_build)
    bars = _bars(10)
    r1 = agent_pipeline._tf_result_memoized("BTCUSD", "1h", bars)
    r2 = agent_pipeline._tf_result_memoized("BTCUSD", "1h", bars)
    assert calls["n"] == 1 and r1 is r2
    agent_pipeline._tf_memo.clear()


def test_tf_memo_different_bars_recompute(monkeypatch):
    agent_pipeline._tf_memo.clear()
    calls = {"n": 0}

    def fake_build(symbol, tf, bars, now=None):
        calls["n"] += 1
        return SimpleNamespace(n=len(bars))

    monkeypatch.setattr(agent_pipeline, "build_timeframe_result", fake_build)
    agent_pipeline._tf_result_memoized("BTCUSD", "1h", _bars(10))
    # Aynı uzunluk/son-ts ama farklı close serisi → parmak izi farklı → yeni hesap.
    agent_pipeline._tf_result_memoized("BTCUSD", "1h", _bars(10, base_close=200.0))
    assert calls["n"] == 2
    agent_pipeline._tf_memo.clear()


# ── S1-4: degraded sağlayıcı sınıflandırması ─────────────────────────────────

def test_degraded_providers_optional_vs_critical():
    from apps.tick_worker.main import _degraded_providers

    snap = SimpleNamespace(
        provider_status={
            "options_deribit": {"status": "degraded"},
            "coingecko": {"status": "ok"},
            "fred": {"status": "down"},
        }
    )
    critical, optional = _degraded_providers(snap)
    assert critical == ["fred"]
    assert optional == ["options_deribit"]


# ── S2-1: RiskEngine MTM drawdown ────────────────────────────────────────────

def _mtm_thresholds():
    return {
        "risk_gates": {
            "max_daily_loss_pct": 0.02,
            "max_drawdown_pct": 0.08,
            "max_open_positions": 6,
        }
    }


def _inp(**kw):
    base = dict(
        dqs_score=90.0,
        equity_usd=100_000.0,
        peak_equity_usd=100_000.0,
        daily_pnl_usd=0.0,
        open_position_count=0,
    )
    base.update(kw)
    return RiskInput(**base)


def test_mtm_tightens_drawdown(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds())
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    d = evaluate(_inp(mtm_equity_usd=90_000.0))
    assert d.action == "KILL_SWITCH"  # H11: max DD = KILL_SWITCH
    assert any("DD(mtm)" in e for e in d.evidence)


def test_mtm_profit_never_relaxes_gate(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds())
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    # Realized %9 dd (fren çeker); MTM karda olsa bile gate GEVŞEMEZ (min()).
    d = evaluate(_inp(equity_usd=91_000.0, mtm_equity_usd=99_000.0))
    assert d.action == "KILL_SWITCH"  # H11: max DD = KILL_SWITCH


def test_mtm_none_is_byte_same(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds())
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    # Ölçüm yoksa (None) drawdown realized equity ile.
    d = evaluate(_inp())
    assert d.action == "HOLD"
