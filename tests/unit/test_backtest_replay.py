"""R2 — deterministic rolling replay / backtest runner testleri.

Hard kurallar:
- Boş store → insufficient_snapshots; tek snapshot → insufficient_future_data.
- Çoklu snapshot → metrikler hesaplanır (deterministik, sabit beklenen değerler).
- Outcome yalnızca GERÇEK gelecek snapshot'larla ölçülür → look-ahead YOK
  (son snapshot'ın sinyali ölçülmez; ölçüm kendi fiyatını değil sonraki
  snapshot'ın fiyatını kullanır).
- Backtest live provider'a DOKUNMAZ (pipeline monkeypatch'i patlatılsa bile çalışır).
- PAPER_SAFE / NO_EXECUTION: paper açılmaz, decide_matrix yeniden çalışmaz.
- /replay/backtest 200 döner; /replay/backtest/{run_id} eşleşmeyince 404.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    d = tmp_path / "snaps"
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(d))
    monkeypatch.delenv("SNAPSHOT_STORE_MAX", raising=False)
    return d


def _client() -> TestClient:
    from apps.api.main import app

    return TestClient(app)


def _payload(sid: str, gen: str, prices: dict[str, float], cells: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": sid,
        "generated_at": gen,
        "mode": {"label": "SIMULATION", "live_data": False},
        "dqs": {"score": 80.0, "status": "OK"},
        "provider_status": {"price": {"status": "ok"}},
        "data_snapshot": {
            "prices": [
                {"symbol": s, "price": p, "verified": True} for s, p in prices.items()
            ],
            "warnings": [],
        },
        "decision_matrix": {
            "regime": "RISK_ON",
            "suspended": False,
            "risk_gate": {"action": "PASS", "reason": "ok"},
            "cells": cells,
            "options": [], "volatility": [], "derivatives": [],
            "catalysts": [], "event_risk": {},
        },
        "risk_state": {"action": "PASS", "reason": "ok", "evidence": []},
        "paper_state_summary": {"equity_usd": 10000.0, "open_position_count": 0,
                                "open_positions": []},
    }


def _signal(symbol: str, tf: str, action: str) -> dict:
    return {"symbol": symbol, "timeframe": tf, "action": action,
            "candidate_action": action, "score": 60, "direction": "long",
            "blocked_by": [], "paper_action": action}


def _blocked(symbol: str, tf: str, candidate: str) -> dict:
    return {"symbol": symbol, "timeframe": tf, "action": "blocked",
            "candidate_action": candidate, "score": 60, "direction": "long",
            "blocked_by": ["risk_gate:NO_POSITION_INCREASE"], "paper_action": "none"}


# ---------- direct runner unit ----------

def test_empty_store_insufficient_snapshots(store_dir) -> None:
    from packages.data import backtest

    out = backtest.run_backtest()
    assert out["status"] == "insufficient_snapshots"
    assert out["available"] is False
    assert out["snapshot_count"] == 0
    assert out["execution"] == "no_live_execution"
    assert out["metrics"]["signals_evaluated"] == 0
    # run_id boş store için bile deterministik (stabil)
    assert out["run_id"] == backtest.run_backtest()["run_id"]


def test_one_snapshot_insufficient_future_data(store_dir) -> None:
    from packages.data import backtest, snapshot_store

    snapshot_store.record(_payload(
        "snap::a", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    out = backtest.run_backtest()
    assert out["status"] == "insufficient_future_data"
    assert out["available"] is False
    assert out["snapshot_count"] == 1
    # tek snapshot: hiçbir sinyal ölçülemez, eksik gelecek dürüstçe sayılır
    assert out["metrics"]["signals_evaluated"] == 0
    assert out["coverage"]["insufficient_future_data"]["total"] >= 1


def test_multiple_snapshots_metrics_computed(store_dir) -> None:
    from packages.data import backtest, snapshot_store

    # BTC & ETH yükselir (+10%/snapshot), SOL düşer (-10%/snapshot).
    seq = [
        ("snap::0", "2026-06-13T00:00:00+00:00", {"BTCUSD": 100.0, "ETHUSD": 100.0, "SOLUSD": 100.0}),
        ("snap::1", "2026-06-13T01:00:00+00:00", {"BTCUSD": 110.0, "ETHUSD": 110.0, "SOLUSD": 90.0}),
        ("snap::2", "2026-06-13T02:00:00+00:00", {"BTCUSD": 121.0, "ETHUSD": 121.0, "SOLUSD": 81.0}),
    ]
    cells = [
        _signal("BTCUSD", "1d", "open_long"),    # yükselen → hit
        _signal("ETHUSD", "4h", "open_short"),   # yükselende short → false positive
        _blocked("SOLUSD", "1h", "open_long"),   # düşeni blokladı → blok doğru
        _blocked("BTCUSD", "4h", "open_long"),   # yükseleni blokladı → false negative
    ]
    for sid, gen, prices in seq:
        snapshot_store.record(_payload(sid, gen, prices, list(cells)))

    out = backtest.run_backtest()
    assert out["status"] == "ok"
    assert out["available"] is True
    assert out["snapshot_count"] == 3

    m = out["metrics"]
    # snap0 & snap1 kararları snap1/snap2 ile ölçülür; her cell 15m+1h horizon
    # çözülür (4h/1d eksik). 2 sinyal × 2 snapshot × 2 horizon = 8 sinyal.
    assert m["signals_evaluated"] == 8
    assert m["hit_rate"] == 0.5            # BTC long hit, ETH short miss
    assert m["false_positive"] == 4
    assert m["suppressed_evaluated"] == 8
    assert m["false_negative"] == 4        # bloklanan BTC long kazanırdı
    assert m["blocked_decision_accuracy"] == 0.5  # SOL blok doğru, BTC blok yanlış
    assert m["avg_return"] == pytest.approx(0.0, abs=1e-9)
    assert m["max_drawdown"] == pytest.approx(0.2, abs=1e-9)

    # per-symbol & per-timeframe dürüst gruplama
    assert out["per_symbol"]["BTCUSD"]["hit_rate"] == 1.0   # BTC long hep hit
    assert out["per_symbol"]["ETHUSD"]["hit_rate"] == 0.0   # ETH short hep miss
    assert "1d" in out["per_timeframe"] and "4h" in out["per_timeframe"]
    assert set(out["per_horizon"].keys()) == {"15m", "1h"}  # sadece bunlar çözüldü
    # 4h/1d her cell için ölçülemedi → dürüstçe coverage'a yazıldı
    assert out["coverage"]["insufficient_future_data"]["per_horizon"]["1d"] > 0


def test_no_look_ahead_last_snapshot_not_measured(store_dir) -> None:
    """Outcome yalnızca GELECEK snapshot'la ölçülür; son snapshot'ın sinyali
    ölçülmez ve ölçüm kendi fiyatını değil sonraki snapshot'ı kullanır."""
    from packages.data import backtest, snapshot_store

    snapshot_store.record(_payload(
        "snap::0", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    snapshot_store.record(_payload(
        "snap::1", "2026-06-13T01:00:00+00:00",
        {"BTCUSD": 200.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    out = backtest.run_backtest()
    # yalnızca snap0'ın sinyali ölçülür (15m + 1h → snap1); snap1 son → ölçülmez
    assert out["metrics"]["signals_evaluated"] == 2
    # ileri ölçüm: snap1 fiyatı (200) ile +1.0 getiri → hit, avg ~ +1.0
    assert out["metrics"]["hit_rate"] == 1.0
    assert out["metrics"]["avg_return"] == pytest.approx(1.0, abs=1e-9)


# ---------- endpoints ----------

def test_backtest_endpoint_empty_and_active(store_dir) -> None:
    from packages.data import snapshot_store

    c = _client()
    r0 = c.get("/api/v1/replay/backtest")
    assert r0.status_code == 200
    assert r0.json()["status"] == "insufficient_snapshots"

    snapshot_store.record(_payload(
        "snap::0", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    snapshot_store.record(_payload(
        "snap::1", "2026-06-13T01:00:00+00:00",
        {"BTCUSD": 110.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    r1 = c.get("/api/v1/replay/backtest")
    assert r1.status_code == 200
    body = r1.json()
    assert body["status"] == "ok"
    assert body["execution"] == "no_live_execution"
    assert body["run_id"]


def test_backtest_run_id_roundtrip_and_404(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload(
        "snap::0", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    snapshot_store.record(_payload(
        "snap::1", "2026-06-13T01:00:00+00:00",
        {"BTCUSD": 110.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    c = _client()
    run_id = c.get("/api/v1/replay/backtest").json()["run_id"]
    ok = c.get(f"/api/v1/replay/backtest/{run_id}")
    assert ok.status_code == 200
    assert ok.json()["run_id"] == run_id

    miss = c.get("/api/v1/replay/backtest/deadbeefdeadbeef")
    assert miss.status_code == 404
    detail = miss.json()["detail"]
    assert detail["status"] == "not_found"
    assert detail["current_run_id"] == run_id


def test_backtest_does_not_refetch_live_data(store_dir, monkeypatch) -> None:
    """Backtest yalnızca store'dan okur — pipeline (live data) çağrılmaz."""
    from packages.data import snapshot_store
    from packages.data.ingestion import pipeline as pl

    snapshot_store.record(_payload(
        "snap::0", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    snapshot_store.record(_payload(
        "snap::1", "2026-06-13T01:00:00+00:00",
        {"BTCUSD": 110.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))

    def _boom(*a, **k):
        raise AssertionError("backtest live data refetch attempted")

    monkeypatch.setattr(pl, "get_cached_snapshot", _boom)
    monkeypatch.setattr(pl, "build_snapshot", _boom)
    c = _client()
    assert c.get("/api/v1/replay/backtest").status_code == 200
    rid = c.get("/api/v1/replay/backtest").json()["run_id"]
    assert c.get(f"/api/v1/replay/backtest/{rid}").status_code == 200


def test_backtest_opens_no_paper_position(store_dir, tmp_path, monkeypatch) -> None:
    """Backtest paper state'i DEĞİŞTİRMEZ (NO_EXECUTION)."""
    from packages.data import snapshot_store
    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "ps.json")
    snapshot_store.record(_payload(
        "snap::0", "2026-06-13T00:00:00+00:00",
        {"BTCUSD": 100.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    snapshot_store.record(_payload(
        "snap::1", "2026-06-13T01:00:00+00:00",
        {"BTCUSD": 110.0}, [_signal("BTCUSD", "1d", "open_long")],
    ))
    _client().get("/api/v1/replay/backtest")
    ps = paper_state.load()
    assert len(ps.open_positions) == 0
