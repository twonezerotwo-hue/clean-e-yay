"""Pipeline + decision + paper smoke testleri."""
from __future__ import annotations


def test_snapshot_pipeline() -> None:
    from packages.data.ingestion.pipeline import build_snapshot

    snap = build_snapshot(["BTCUSD", "ETHUSD", "XAUUSD"])
    assert snap.snapshot_id.startswith("snap::")
    assert snap.prices and snap.prices[0].price > 0
    assert snap.headlines
    assert snap.catalysts
    assert 0 <= snap.quality.score <= 100


def test_regime_and_consensus() -> None:
    from packages.consensus.engine import build as build_consensus
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    assert regime.label in {"OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"}
    cons = build_consensus("BTCUSD", snap, regime)
    assert 0 <= cons.score <= 100
    assert cons.direction in {"bullish", "bearish", "neutral"}
    assert cons.modules


def test_decision_engine_no_exception() -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_all
    from packages.risk.engine import RiskInput

    snap = build_snapshot(["BTCUSD", "ETHUSD"])
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )
    regime, risk, decisions = decide_all(["BTCUSD", "ETHUSD"], snap, risk_in)
    assert regime.label
    assert risk.action
    assert len(decisions) == 2
    for d in decisions:
        assert d.action in {"open_long", "open_short", "hold", "blocked"}


def test_paper_lifecycle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "state.json"))
    # Reload module to pick up new env
    import importlib
    from packages.paper import state as st
    importlib.reload(st)
    from packages.paper.lifecycle import open_position, tick

    s = st.load()
    pos = open_position(
        s,
        symbol="BTCUSD",
        side="long",
        entry_price=100.0,
        size_multiplier=1.0,
    )
    assert pos.sl < pos.entry_price
    assert pos.tp > pos.entry_price
    # tick aşağı doğru — SL tetikle
    trades = tick(s, {"BTCUSD": pos.sl - 0.5})
    assert trades and trades[0].close_reason == "SL_HIT"
    assert s.open_positions == []
    # PnL negatif olmalı
    assert s.realized_pnl_usd < 0


def test_api_endpoints() -> None:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    for path in [
        "/api/v1/health",
        "/api/v1/regime-report/current",
        "/api/v1/dashboard/state",
        "/api/v1/ai-report/current",
        "/api/v1/paper-trading/state",
        "/api/v1/learning/summary",
    ]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert isinstance(body, dict)


# T1 (2026-07 dış denetim): test_paper_tick_endpoint SİLİNDİ — POST
# /paper-trading/tick sözleşmeden kaldırıldı (tek tick yolu apps/tick_worker;
# worker pass'inin davranış testleri: test_halt, test_providers,
# test_timeframe_decisions, test_tick_worker_observe).
