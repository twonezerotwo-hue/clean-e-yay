"""Canlı-config smoke — F5 (EV kapısı + Kelly) + tüm guard'lar GERÇEK config haliyle
decision pipeline'ı çalıştırır.

conftest._f5_disabled_by_default F5'i unit testlerde KAPATIR (pre-F5 sizing varsayan
testleri korumak için). Bu, suite ile canlı config arasında sapma yaratır: CI yeşil
olsa da canlı davranış doğrulanmamış olur. Bu test gerçek config'i GERİ AÇAR ve canlı
decision pipeline'ının crash etmeden, sınırlar içinde, tutarlı karar ürettiğini
doğrular (suite↔prod sapmasını kapatır).
"""
from __future__ import annotations

import importlib

from packages.data.ingestion.pipeline import build_snapshot
from packages.data.registry.loader import load_thresholds
from packages.decision import engine
from packages.decision.engine import decide_matrix, matrix_view
from packages.risk.engine import RiskInput


def _risk_in() -> RiskInput:
    return RiskInput(
        dqs_score=90.0, equity_usd=100_000, peak_equity_usd=100_000,
        daily_pnl_usd=0, open_position_count=0,
    )


def test_live_config_decision_pipeline_smoke(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    # conftest F5'i kapatmıştı — GERÇEK config'i geri aç (canlı davranışı doğrula).
    monkeypatch.setattr(engine, "_ev_gate_cfg", lambda: load_thresholds().get("ev_gate") or {})
    monkeypatch.setattr(engine, "_kelly_cfg", lambda: load_thresholds().get("kelly_sizing") or {})

    snap = build_snapshot(["BTCUSD"])
    regime, risk, decisions = decide_matrix(["BTCUSD"], snap, _risk_in())
    vm = matrix_view(regime, risk, decisions, snap, ["BTCUSD"])

    assert len(vm["cells"]) == 5  # 5 TF — pipeline crash etmedi
    ev_cfg = load_thresholds().get("ev_gate") or {}
    ev_on = bool(ev_cfg.get("enabled"))
    min_ev = float(ev_cfg.get("min_ev", 0.0))
    for d in decisions:
        assert 0.0 <= d.size_multiplier <= 1.5  # boyut sınırları (cap'ler asla taşmaz)
        if d.action in ("open_long", "open_short"):
            assert d.expected_value is not None  # açık karar EV taşır
            if ev_on:
                # ev_gate açıkken negatif-EV açılış OLAMAZ (olsaydı bloklanırdı)
                assert d.expected_value >= min_ev
    for c in vm["cells"]:
        assert "expected_value" in c  # dashboard gözlem alanı
