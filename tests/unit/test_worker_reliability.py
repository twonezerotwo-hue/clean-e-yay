"""O1 — worker reliability (heartbeat + system health) testleri.

- heartbeat write/read atomic; missing → default; corrupt → safe default.
- cycle_count terminal'de artar; last_success_at OK'te güncellenir, FAILED'de korunur.
- tick worker success → OK/DEGRADED heartbeat; exception → FAILED (loop ölmez).
- learning worker empty data → NO_DATA heartbeat (crash yok).
- stale detection (system_health) + system/health endpoint worker statüleri.
- live network yok (conftest TEST_USE_MOCK=true).
"""
from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", str(tmp_path / "heartbeats.json"))
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper_state.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "paper_audit.jsonl"))
    monkeypatch.setenv("RISK_HALT_PATH", str(tmp_path / "risk_halts.json"))
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "snapshots"))
    monkeypatch.setenv("LEARNING_RUN_PATH", str(tmp_path / "learning_run.json"))
    monkeypatch.setenv("LEARNING_OUT_PATH", str(tmp_path / "learning_summary.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return tmp_path


def _utc_iso(delta_sec: float = 0.0) -> str:
    return (datetime.now(UTC) - timedelta(seconds=delta_sec)).isoformat()


# ------------------------------- heartbeat store -----------------------------

def test_heartbeat_write_read(ops_env) -> None:
    from packages.ops import heartbeat
    hb = heartbeat.record(
        "tick_worker", status="OK", run_id="r1",
        started_at=_utc_iso(1), completed_at=_utc_iso(),
        snapshots_written=1, decisions_generated=20, paper_actions=2,
    )
    assert hb["status"] == "OK"
    loaded = heartbeat.load("tick_worker")
    assert loaded is not None
    assert loaded["run_id"] == "r1"
    assert loaded["cycle_count"] == 1
    assert loaded["snapshots_written"] == 1
    assert loaded["last_success_at"] is not None


def test_heartbeat_missing_file_default(ops_env) -> None:
    from packages.ops import heartbeat
    assert heartbeat.load_all() == {}
    assert heartbeat.load("tick_worker") is None


def test_heartbeat_corrupt_file_safe_default(ops_env, monkeypatch) -> None:
    from packages.ops import heartbeat
    path = ops_env / "heartbeats.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    # corrupt → default (crash yok)
    assert heartbeat.load_all() == {}
    # bir sonraki record temiz yazar
    heartbeat.record("tick_worker", status="OK", run_id="r", started_at=_utc_iso())
    assert heartbeat.load("tick_worker")["status"] == "OK"


def test_heartbeat_cycle_count_and_last_success(ops_env) -> None:
    from packages.ops import heartbeat
    # RUNNING terminal değil → cycle_count artmaz, last_success_at None
    heartbeat.record("w", status="RUNNING", run_id="r1", started_at=_utc_iso(2))
    assert heartbeat.load("w")["cycle_count"] == 0
    # OK → cycle_count 1 + last_success_at set
    heartbeat.record("w", status="OK", run_id="r1", started_at=_utc_iso(2), completed_at=_utc_iso())
    ok = heartbeat.load("w")
    assert ok["cycle_count"] == 1
    success_ts = ok["last_success_at"]
    assert success_ts is not None
    # FAILED → cycle_count 2 ama last_success_at KORUNUR
    heartbeat.record("w", status="FAILED", run_id="r2", started_at=_utc_iso(1),
                     completed_at=_utc_iso(), last_error="boom")
    failed = heartbeat.load("w")
    assert failed["cycle_count"] == 2
    assert failed["status"] == "FAILED"
    assert failed["last_error"] == "boom"
    assert failed["last_success_at"] == success_ts  # korundu


# ------------------------------ system health VM -----------------------------

def test_stale_detection(ops_env) -> None:
    from packages.ops import heartbeat, system_health
    # tick: 10 dk önce OK → default eşik 120s → STALE
    heartbeat.record("tick_worker", status="OK", run_id="r", started_at=_utc_iso(605),
                     completed_at=_utc_iso(600))
    sh = system_health.build_system_health()
    tick = sh["workers"]["tick_worker"]
    assert tick["stale"] is True
    assert tick["status"] == "STALE"
    assert "worker_stale" in sh["warnings"]
    # learning: hiç çalışmadı → UNKNOWN + stale
    assert sh["workers"]["learning_worker"]["status"] == "UNKNOWN"
    assert sh["workers"]["learning_worker"]["stale"] is True


def test_fresh_worker_not_stale(ops_env) -> None:
    from packages.ops import heartbeat, system_health
    heartbeat.record("tick_worker", status="OK", run_id="r", started_at=_utc_iso(1),
                     completed_at=_utc_iso())
    tick = system_health.build_system_health()["workers"]["tick_worker"]
    assert tick["stale"] is False
    assert tick["status"] == "OK"


def test_system_health_paper_safe_flags(ops_env) -> None:
    from packages.ops import system_health
    sh = system_health.build_system_health()
    assert sh["paper_safe"] is True
    assert sh["no_execution"] is True
    assert "snapshot_store_empty" in sh["warnings"]  # izole store boş


# ------------------------------ tick worker hb -------------------------------

def test_tick_worker_success_writes_ok_heartbeat(ops_env) -> None:
    from apps.tick_worker import main as tw
    from packages.ops import heartbeat
    asyncio.run(tw.run_once())
    hb = heartbeat.load("tick_worker")
    assert hb is not None
    assert hb["status"] in {"OK", "DEGRADED"}  # başarılı cycle (FAILED değil)
    assert hb["cycle_count"] >= 1
    assert hb["last_success_at"] is not None


def test_tick_worker_exception_writes_failed_heartbeat(ops_env, monkeypatch) -> None:
    from apps.tick_worker import main as tw
    from packages.ops import heartbeat

    def boom():
        raise RuntimeError("snapshot blew up")

    monkeypatch.setattr(tw, "get_cached_snapshot", boom)
    # run_once istisnayı yutar (loop ölmez) ve FAILED heartbeat yazar
    asyncio.run(tw.run_once())
    hb = heartbeat.load("tick_worker")
    assert hb is not None
    assert hb["status"] == "FAILED"
    assert "snapshot blew up" in (hb["last_error"] or "")


# ---------------------------- learning worker hb -----------------------------

def test_learning_worker_empty_data_writes_no_data_heartbeat(ops_env) -> None:
    from apps.learning_worker import main as lw
    importlib.reload(lw)
    run = lw.run_once()
    assert run["status"] == "NO_DATA"
    from packages.ops import heartbeat
    hb = heartbeat.load("learning_worker")
    assert hb is not None
    assert hb["status"] == "NO_DATA"
    assert hb["learning_outcomes_seen"] == 0
    assert hb["cycle_count"] >= 1


# ------------------------------- endpoint ------------------------------------

def test_system_health_endpoint_returns_worker_statuses(ops_env) -> None:
    from packages.ops import heartbeat
    heartbeat.record("tick_worker", status="OK", run_id="r", started_at=_utc_iso(1),
                     completed_at=_utc_iso())
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["paper_safe"] is True
    assert body["no_execution"] is True
    assert "tick_worker" in body["workers"]
    assert "learning_worker" in body["workers"]
    assert body["workers"]["tick_worker"]["worker_name"] == "tick_worker"
    assert "warnings" in body
    assert isinstance(body["warnings"], list)
