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

from packages.decision import agent_pipeline, shadow
from packages.risk.engine import RiskInput, evaluate

# ── S1-2: shadow tail-read + rotasyon ────────────────────────────────────────

def _write_records(path, start, count):
    with path.open("a", encoding="utf-8") as f:
        for i in range(start, start + count):
            f.write(json.dumps({"i": i}) + "\n")


def test_shadow_read_recent_tail(tmp_path, monkeypatch):
    p = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("SHADOW_LOG_PATH", str(p))
    _write_records(p, 0, 500)
    out = shadow.read_recent(limit=10)
    assert [r["i"] for r in out] == list(range(490, 500))


def test_shadow_rotation_and_archive_spanning(tmp_path, monkeypatch):
    p = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("SHADOW_LOG_PATH", str(p))
    # Tavanı minik yap: ilk record çağrısı mevcut dosyayı .1'e devirir.
    monkeypatch.setenv("SHADOW_LOG_MAX_MB", "0.0001")
    _write_records(p, 0, 50)
    shadow.record({"i": 50})
    assert p.with_name(p.name + ".1").exists()
    # Aktif dosyada 1 kayıt var; okuyucu arşive uzanıp aynı kümeyi döner.
    out = shadow.read_recent(limit=5)
    assert [r["i"] for r in out] == [46, 47, 48, 49, 50]


def test_shadow_read_recent_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "yok.jsonl"))
    assert shadow.read_recent(limit=5) == []


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

def _mtm_thresholds(enabled):
    return {
        "risk_gates": {
            "max_daily_loss_pct": 0.02,
            "max_drawdown_pct": 0.08,
            "max_open_positions": 6,
            "mtm_equity_enabled": enabled,
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


def test_mtm_flag_off_ignores_mtm(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds(False))
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    # MTM %10 ekside ama flag kapalı → drawdown realized'a göre (0) → HOLD.
    d = evaluate(_inp(mtm_equity_usd=90_000.0))
    assert d.action == "HOLD"


def test_mtm_flag_on_tightens_drawdown(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds(True))
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    d = evaluate(_inp(mtm_equity_usd=90_000.0))
    assert d.action == "RISK_REDUCE"
    assert any("DD(mtm)" in e for e in d.evidence)


def test_mtm_profit_never_relaxes_gate(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds(True))
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    # Realized %9 dd (fren çeker); MTM karda olsa bile gate GEVŞEMEZ (min()).
    d = evaluate(_inp(equity_usd=91_000.0, mtm_equity_usd=99_000.0))
    assert d.action == "RISK_REDUCE"


def test_mtm_none_is_byte_same(monkeypatch):
    import packages.risk.engine as eng

    monkeypatch.setattr(eng, "load_thresholds", lambda: _mtm_thresholds(True))
    monkeypatch.setattr(eng.halt_store, "active_halts", list)
    # Ölçüm yoksa (None — eski çağıranlar) flag açık bile olsa davranış eski.
    d = evaluate(_inp())
    assert d.action == "HOLD"
