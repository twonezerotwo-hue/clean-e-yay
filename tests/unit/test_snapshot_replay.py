"""R1 — gerçek snapshot replay foundation testleri.

Hard kurallar:
- Atomik write; bozuk dosya → crash yok; latest + id ile okuma.
- Replay endpoint'leri live data REFETCH ETMEZ (yalnızca store'dan okur).
- Decision-trace stored decision_matrix'i kullanır; yeni karar hesaplamaz.
- Sahte backtest yok; boş store dürüstçe empty/insufficient_snapshots der.
- Testlerde live network yok (TEST_USE_MOCK + store temp dir).
"""
from __future__ import annotations

import json

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


def _payload(sid: str, gen: str, *, cells=None, mode=None) -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": sid,
        "generated_at": gen,
        "mode": mode or {"label": "SIMULATION", "live_data": False},
        "dqs": {"score": 72.0, "status": "DEGRADED"},
        "provider_status": {"deribit": {"status": "degraded"}, "price": {"status": "ok"}},
        "data_snapshot": {"prices": [{"symbol": "BTCUSD", "price": 1.0, "verified": True}],
                          "warnings": []},
        "decision_matrix": {
            "regime": "RISK_ON",
            "suspended": False,
            "risk_gate": {"action": "PASS", "reason": "ok"},
            "cells": cells if cells is not None else [
                {"symbol": "BTCUSD", "timeframe": "4h", "action": "blocked",
                 "candidate_action": "open_long", "score": 64, "direction": "long",
                 "blocked_by": ["options_risk:PUT_SKEW_STRESS"], "paper_action": "none"},
                {"symbol": "ETHUSD", "timeframe": "1d", "action": "open_long",
                 "candidate_action": "open_long", "score": 58, "direction": "long",
                 "blocked_by": [], "paper_action": "open_long"},
            ],
            "options": [{"symbol": "BTCUSD", "regime": "PUT_SKEW_STRESS"}],
            "volatility": [], "derivatives": [], "catalysts": [], "event_risk": {},
        },
        "risk_state": {"action": "PASS", "reason": "ok", "evidence": []},
        "paper_state_summary": {"equity_usd": 10000.0, "open_position_count": 0,
                                "open_positions": []},
    }


# ---------- store unit ----------

def test_record_atomic_and_latest(store_dir) -> None:
    from packages.data import snapshot_store

    sid = snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    assert sid == "snap::aaa"
    # atomik: hiçbir .tmp dosyası kalmaz
    assert not list(store_dir.glob("*.tmp*"))
    assert snapshot_store.count() == 1
    latest = snapshot_store.latest()
    assert latest is not None and latest["snapshot_id"] == "snap::aaa"
    assert latest["schema_version"] == 1


def test_get_by_id_and_missing(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    snapshot_store.record(_payload("snap::bbb", "2026-06-13T00:00:02"))
    got = snapshot_store.get("snap::aaa")
    assert got is not None and got["snapshot_id"] == "snap::aaa"
    assert snapshot_store.get("snap::nope") is None


def test_corrupted_file_skipped_no_crash(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::good", "2026-06-13T00:00:01"))
    # daha geç sıralanan bozuk dosya — latest onu atlamalı
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "99999999__snap__bad.json").write_text("{ this is not json",
                                                        encoding="utf-8")
    latest = snapshot_store.latest()  # crash YOK
    assert latest is not None and latest["snapshot_id"] == "snap::good"
    assert snapshot_store.get("snap::bad") is None


def test_record_dedup_same_id(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:09"))
    assert snapshot_store.count() == 1  # aynı id en güncelse tekrar yazılmaz


def test_prune_respects_max(store_dir, monkeypatch) -> None:
    from packages.data import snapshot_store

    monkeypatch.setenv("SNAPSHOT_STORE_MAX", "2")
    snapshot_store.record(_payload("snap::a1", "2026-06-13T00:00:01"))
    snapshot_store.record(_payload("snap::a2", "2026-06-13T00:00:02"))
    snapshot_store.record(_payload("snap::a3", "2026-06-13T00:00:03"))
    assert snapshot_store.count() == 2
    assert snapshot_store.get("snap::a1") is None  # en eski budandı
    assert snapshot_store.get("snap::a3") is not None


def test_status_empty_and_active(store_dir) -> None:
    from packages.data import snapshot_store

    st = snapshot_store.status()
    assert st["snapshot_count"] == 0 and st["latest_snapshot_id"] is None
    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    st2 = snapshot_store.status()
    assert st2["snapshot_count"] == 1 and st2["latest_snapshot_id"] == "snap::aaa"


# ---------- replay endpoints ----------

def test_replay_status_endpoint_empty(store_dir) -> None:
    r = _client().get("/api/v1/replay/status")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "empty"
    assert b["available"] is False
    assert b["mode"] == "insufficient_snapshots"
    assert b["snapshot_count"] == 0
    assert b["execution"] == "no_live_execution"


def test_replay_status_endpoint_active(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    r = _client().get("/api/v1/replay/status")
    b = r.json()
    assert b["status"] == "active"
    assert b["available"] is True
    assert b["mode"] == "active_snapshot_replay"
    assert b["snapshot_count"] == 1
    assert b["latest_snapshot_id"] == "snap::aaa"


def test_replay_snapshot_found_and_404(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    c = _client()
    ok = c.get("/api/v1/replay/snap::aaa")
    assert ok.status_code == 200
    body = ok.json()
    assert body["available"] is True
    assert body["snapshot"]["snapshot_id"] == "snap::aaa"
    assert body["snapshot"]["decision_matrix"]["regime"] == "RISK_ON"
    assert c.get("/api/v1/replay/snap::missing").status_code == 404


def test_replay_decision_trace_uses_stored_matrix(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    r = _client().get("/api/v1/replay/snap::aaa/decision-trace")
    assert r.status_code == 200
    t = r.json()
    assert t["snapshot_id"] == "snap::aaa"
    assert t["regime"] == "RISK_ON"
    assert "options_risk:PUT_SKEW_STRESS" in t["blocked_by_reasons"]
    assert any(c["symbol"] == "BTCUSD" for c in t["top_candidates"])
    assert any(a["symbol"] == "ETHUSD" for a in t["paper_actions"])
    assert t["deep_data"]["options"] == [{"symbol": "BTCUSD", "regime": "PUT_SKEW_STRESS"}]
    # provider issue (degraded) yüzeye çıkar; ok olan gizlenir
    assert "deribit" in t["provider_issues"] and "price" not in t["provider_issues"]
    assert t["execution"] == "no_live_execution"
    assert _client().get("/api/v1/replay/snap::x/decision-trace").status_code == 404


def test_replay_endpoints_do_not_refetch_live_data(store_dir, monkeypatch) -> None:
    """Replay yalnızca store'dan okur — pipeline'a (live data) DOKUNMAZ."""
    from packages.data import snapshot_store
    from packages.data.ingestion import pipeline as pl

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))

    def _boom(*a, **k):
        raise AssertionError("replay live data refetch attempted")

    monkeypatch.setattr(pl, "get_cached_snapshot", _boom)
    monkeypatch.setattr(pl, "build_snapshot", _boom)
    c = _client()
    assert c.get("/api/v1/replay/status").status_code == 200
    assert c.get("/api/v1/replay/snap::aaa").status_code == 200
    assert c.get("/api/v1/replay/snap::aaa/decision-trace").status_code == 200


# ---------- producer (tick_worker) integration, offline ----------

def test_tick_worker_records_snapshot(store_dir, tmp_path, monkeypatch) -> None:
    """run_once() gerçek decide_matrix çıktısını store'a yazar (offline mock)."""
    import asyncio

    from packages.paper import state as paper_state

    monkeypatch.setattr(paper_state, "STATE_PATH", tmp_path / "ps.json")
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "halts.json"))

    from apps.tick_worker.main import run_once
    from packages.data import snapshot_store

    asyncio.run(run_once())
    assert snapshot_store.count() >= 1
    latest = snapshot_store.latest()
    assert latest is not None
    assert "decision_matrix" in latest and "cells" in latest["decision_matrix"]
    assert "paper_state_summary" in latest
    # stored snapshot decision-trace üzerinden okunabilir olmalı
    r = _client().get(f"/api/v1/replay/{latest['snapshot_id']}/decision-trace")
    assert r.status_code == 200


# ---------- corrupted store does not break status endpoint ----------

def test_replay_status_with_corrupted_only_store(store_dir) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "20260613T000001__snap__x.json").write_text("broken", encoding="utf-8")
    r = _client().get("/api/v1/replay/status")
    assert r.status_code == 200
    b = r.json()
    # dosya var ama okunamıyor → latest None; count dosya sayısını yansıtır (crash yok)
    assert b["snapshot_count"] == 1
    assert b["latest_snapshot_id"] is None


def test_store_json_is_valid_roundtrip(store_dir) -> None:
    from packages.data import snapshot_store

    snapshot_store.record(_payload("snap::aaa", "2026-06-13T00:00:01"))
    files = list(store_dir.glob("*.json"))
    assert len(files) == 1
    parsed = json.loads(files[0].read_text(encoding="utf-8"))
    assert parsed["snapshot_id"] == "snap::aaa"
