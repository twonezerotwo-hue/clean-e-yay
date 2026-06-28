"""Part 2 — Governor görev kuyruğu (observe-only) testleri.

Kapsam:
- enqueue: geçerli/geçersiz tip, dedup, can_change_policy YAPISAL False.
- list_queue öncelik sırası (P0 önce).
- execute: read-only rapor üretir, DONE/FAILED, bulunamazsa None.
- DEĞİŞMEZ: hiçbir handler config/paper yazmaz (mode store override'ı oluşmaz).
- generate: store sinyallerinden görev üretir, dedup'lu, crash-safe.
- endpoint GET/POST/generate/run + 422/404.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNOR_TASKS_PATH", str(tmp_path / "governor_tasks.json"))
    return tmp_path


# ----------------- enqueue / invariant -----------------

def test_enqueue_roundtrip(iso) -> None:
    from packages.governor import tasks
    t = tasks.enqueue("DATA_QUALITY_REVIEW", subject="x")
    assert t is not None
    assert t["status"] == "PENDING"
    assert t["priority"] == "P0"
    assert tasks.list_queue()[0]["task_id"] == t["task_id"]


def test_enqueue_rejects_unknown_type(iso) -> None:
    from packages.governor import tasks
    assert tasks.enqueue("BOGUS_REVIEW") is None
    assert tasks.list_queue() == []


def test_can_change_policy_is_structurally_false(iso) -> None:
    """Girdide can_change_policy=True gelse bile görevde False olmalı (enqueue
    bu alanı girdiden okumaz)."""
    from packages.governor import tasks
    # enqueue imzası can_change_policy almıyor; params içine sokulsa da görev
    # alanına yansımaz.
    t = tasks.enqueue("TRADE_REVIEW", params={"can_change_policy": True})
    assert t["can_change_policy"] is False


def test_enqueue_dedup(iso) -> None:
    from packages.governor import tasks
    a = tasks.enqueue("RISK_REVIEW", params={"k": 1})
    b = tasks.enqueue("RISK_REVIEW", params={"k": 1})
    assert a["task_id"] == b["task_id"]
    assert len(tasks.list_queue()) == 1


def test_list_queue_priority_order(iso) -> None:
    from packages.governor import tasks
    tasks.enqueue("SYSTEM_HEALTH_REVIEW")  # P4
    tasks.enqueue("DATA_QUALITY_REVIEW")  # P0
    tasks.enqueue("MISSED_OPPORTUNITY_REVIEW")  # P2
    prios = [t["priority"] for t in tasks.list_queue()]
    assert prios == ["P0", "P2", "P4"]


# ----------------- execute -----------------

def test_execute_produces_readonly_report(iso, monkeypatch) -> None:
    from packages.governor import tasks
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    t = tasks.enqueue("MODE_REVIEW")
    done = tasks.execute(t["task_id"])
    assert done["status"] == "DONE"
    assert isinstance(done["result"], dict)
    assert "disabled_trade_profiles" in done["result"]
    # kuyruktan çıktı, history'e girdi
    assert tasks.list_queue() == []
    assert tasks.load()["history"][0]["task_id"] == t["task_id"]


def test_execute_unknown_id_returns_none(iso) -> None:
    from packages.governor import tasks
    assert tasks.execute("nope") is None


def test_execute_does_not_write_config(iso, tmp_path, monkeypatch) -> None:
    """DEĞİŞMEZ: MODE_REVIEW görevini koşmak agent_mode override'ı OLUŞTURMAZ."""
    from packages.governor import tasks
    from packages.mode import store as mode_store

    monkeypatch.setenv("AGENT_MODE_STORE_PATH", str(tmp_path / "agent_mode.json"))
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    t = tasks.enqueue("MODE_REVIEW")
    tasks.execute(t["task_id"])
    assert mode_store.load_overrides() == {}  # hiçbir config yazılmadı


def test_execute_handler_failure_is_safe(iso, monkeypatch) -> None:
    """Handler patlarsa görev FAILED olur ama kuyruk bozulmaz."""
    from packages.governor import tasks

    def _boom(_params):
        raise RuntimeError("patladı")

    monkeypatch.setitem(tasks._HANDLERS, "TRADE_REVIEW", _boom)
    t = tasks.enqueue("TRADE_REVIEW")
    done = tasks.execute(t["task_id"])
    assert done["status"] == "FAILED"
    assert "patladı" in done["result"]["error"]


# ----------------- generate -----------------

def test_generate_is_crash_safe(iso, monkeypatch) -> None:
    from packages.governor import tasks
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    # Sadece patlamamalı ve list dönmeli (içerik ortama bağlı).
    created = tasks.generate()
    assert isinstance(created, list)


def test_generate_dedups_on_repeat(iso, monkeypatch) -> None:
    from packages.governor import tasks
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    first = tasks.generate()
    before = len(tasks.list_queue())
    tasks.generate()  # ikinci tur aynı sinyaller → çift eklememeli
    after = len(tasks.list_queue())
    assert after == before
    assert isinstance(first, list)


# ----------------- corrupt-safe -----------------

def test_corrupt_store_safe(iso) -> None:
    from packages.governor import tasks
    (iso / "governor_tasks.json").write_text("{bozuk", encoding="utf-8")
    assert tasks.load() == {"queue": [], "history": []}
    assert tasks.enqueue("RISK_REVIEW") is not None


# ----------------- endpoint -----------------

def test_endpoints_roundtrip(iso, monkeypatch) -> None:
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    from fastapi.testclient import TestClient

    from apps.api.main import app
    c = TestClient(app)

    g = c.get("/api/v1/governor/tasks")
    assert g.status_code == 200
    assert g.json()["queue_count"] == 0

    bad = c.post("/api/v1/governor/tasks", json={"task_type": "NOPE"})
    assert bad.status_code == 422

    sub = c.post("/api/v1/governor/tasks", json={"task_type": "SYSTEM_HEALTH_REVIEW"})
    assert sub.status_code == 200
    tid = sub.json()["task"]["task_id"]
    assert sub.json()["task"]["can_change_policy"] is False

    gen = c.post("/api/v1/governor/tasks/generate")
    assert gen.status_code == 200
    assert "generated" in gen.json()

    run = c.post(f"/api/v1/governor/tasks/{tid}/run")
    assert run.status_code == 200
    assert run.json()["task"]["status"] in {"DONE", "FAILED"}

    # tekrar run → 404 (artık kuyrukta değil)
    assert c.post(f"/api/v1/governor/tasks/{tid}/run").status_code == 404
