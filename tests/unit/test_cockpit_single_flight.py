"""Kokpit özeti tek uçuş: soğuk açılışta eşzamanlı istekler tek derlemeyi paylaşır.

Yeniden başlatmadan sonra ekranlar + SSR aynı anda /cockpit/state istiyordu;
her biri ayrı derleme başlatıp GIL'de birbirini yavaşlatıyordu (5 sn → 55 sn+).
"""
from __future__ import annotations

import threading
import time

import pytest

from apps.api.routers import cockpit


def _join_cockpit_threads() -> None:
    """Önceki testlerden kalan arka plan yenilemesi sayımı bozmasın."""
    for t in threading.enumerate():
        if t.name.startswith("cockpit-brief-") and t is not threading.current_thread():
            t.join(timeout=30)


@pytest.fixture
def empty_cache(monkeypatch):
    _join_cockpit_threads()
    monkeypatch.setattr(cockpit, "_BRIEF_CACHE", None)
    monkeypatch.setattr(cockpit, "_BRIEF_REFRESHING", False)
    monkeypatch.setattr(cockpit, "_BUILD_LOCK", threading.Lock())
    monkeypatch.setattr(cockpit, "_RESTORED", False)
    monkeypatch.setattr(cockpit, "_DISK_LAST_SAVE", 0.0)
    yield
    _join_cockpit_threads()


def _counting_builder(monkeypatch, delay: float = 0.3) -> list[int]:
    builds: list[int] = []

    def slow_build() -> dict:
        builds.append(1)
        time.sleep(delay)
        return {"n": len(builds)}

    monkeypatch.setattr(cockpit, "_build_cockpit_brief", slow_build)
    return builds


def test_concurrent_cold_requests_share_one_build(empty_cache, monkeypatch):
    builds = _counting_builder(monkeypatch)
    results: list[dict] = []
    threads = [
        threading.Thread(target=lambda: results.append(cockpit.get_cockpit_state()))
        for _ in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(builds) == 1, f"tek derleme beklenirdi, {len(builds)} oldu"
    assert len(results) == 6
    assert all(r == {"n": 1} for r in results)


def test_warm_builds_once_and_cold_request_waits_for_it(empty_cache, monkeypatch):
    builds = _counting_builder(monkeypatch)
    cockpit.warm()
    cockpit.warm()  # ikinci çağrı yeni derleme başlatmaz
    time.sleep(0.05)  # ısıtma derlemesi kilidi alsın

    assert cockpit.get_cockpit_state() == {"n": 1}
    assert len(builds) == 1


def test_warm_is_noop_when_cache_present(empty_cache, monkeypatch):
    builds = _counting_builder(monkeypatch)
    monkeypatch.setattr(cockpit, "_BRIEF_CACHE", (time.monotonic(), {"cached": True}))
    cockpit.warm()
    assert cockpit.get_cockpit_state() == {"cached": True}
    assert builds == []


def test_failed_warm_falls_back_to_synchronous_build(empty_cache, monkeypatch):
    calls: list[int] = []

    def flaky_build() -> dict:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("ilk derleme düştü")
        return {"ok": True}

    monkeypatch.setattr(cockpit, "_build_cockpit_brief", flaky_build)
    cockpit.warm()
    deadline = time.monotonic() + 5
    while cockpit._BRIEF_REFRESHING and time.monotonic() < deadline:
        time.sleep(0.01)

    assert cockpit.get_cockpit_state() == {"ok": True}
    assert len(calls) == 2


def test_supervisor_warms_after_server_starts(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from apps.supervisor import main as sup

    warmed: list[tuple[float, float]] = []
    monkeypatch.setattr(cockpit, "warm", lambda wait: warmed.append((time.monotonic(), wait)))
    server = SimpleNamespace(started=False)

    async def scenario() -> float:
        task = asyncio.create_task(sup._warm_cockpit(server, wait_tick_sec=120.0, timeout=5))
        await asyncio.sleep(0.2)
        assert warmed == [], "API dinlemeden ısıtma başlamaz"
        server.started = True
        started_at = time.monotonic()
        await asyncio.wait_for(task, timeout=3)
        return started_at

    started_at = asyncio.run(scenario())
    assert len(warmed) == 1 and warmed[0][0] >= started_at
    assert warmed[0][1] == 120.0


def test_warm_waits_for_tick_snapshot_and_cold_request_shares_it(empty_cache, monkeypatch):
    """Açılışta özet tick'in görüntüsünü bekler; arada gelen istek aynı derlemeyi bekler."""
    from packages.data.ingestion import pipeline

    tick_snap: list[object] = []
    monkeypatch.setattr(
        pipeline, "latest_tick_snapshot", lambda: tick_snap[0] if tick_snap else None
    )
    seen: list[bool] = []

    def build() -> dict:
        seen.append(bool(tick_snap))
        return {"from_tick": bool(tick_snap)}

    monkeypatch.setattr(cockpit, "_build_cockpit_brief", build)
    cockpit.warm(wait_tick_sec=10)
    threading.Timer(0.4, lambda: tick_snap.append(object())).start()
    time.sleep(0.05)
    assert cockpit.get_cockpit_state() == {"from_tick": True}
    assert seen == [True], "derleme tick görüntüsünden önce başlamamalı ve tek olmalı"


def test_warm_builds_anyway_when_tick_never_publishes(empty_cache, monkeypatch):
    from packages.data.ingestion import pipeline

    monkeypatch.setattr(pipeline, "latest_tick_snapshot", lambda: None)
    builds = _counting_builder(monkeypatch, delay=0.0)
    cockpit.warm(wait_tick_sec=0.6)
    started = time.monotonic()
    assert cockpit.get_cockpit_state() == {"n": 1}
    assert 0.4 < time.monotonic() - started < 5
    assert len(builds) == 1


# ── Hızlı açılış: son özet diskte, yeniden başlatmada hemen sunulur ──────────────


@pytest.fixture
def disk_copy(empty_cache, monkeypatch, tmp_path):
    path = tmp_path / "cockpit_brief_last.json"
    monkeypatch.setenv("COCKPIT_BRIEF_DISK_PATH", str(path))
    return path


def _simulate_restart(monkeypatch) -> None:
    monkeypatch.setattr(cockpit, "_BRIEF_CACHE", None)
    monkeypatch.setattr(cockpit, "_BRIEF_REFRESHING", False)
    monkeypatch.setattr(cockpit, "_RESTORED", False)
    monkeypatch.setattr(cockpit, "_DISK_LAST_SAVE", 0.0)


def test_build_writes_disk_copy_and_restart_serves_it_without_building(disk_copy, monkeypatch):
    builds = _counting_builder(monkeypatch, delay=0.0)
    first = cockpit.get_cockpit_state()
    assert first == {"n": 1}
    assert disk_copy.exists()

    _simulate_restart(monkeypatch)
    assert cockpit.restore_from_disk() is True
    started = time.monotonic()
    assert cockpit.get_cockpit_state() == {"n": 1}
    assert time.monotonic() - started < 0.5
    assert len(builds) == 1, "geri yüklenen kopya istekte yeni derleme başlatmamalı"
    assert cockpit._BRIEF_REFRESHING is False


def test_restored_copy_is_served_while_warm_builds_then_replaced(disk_copy, monkeypatch):
    import json
    from datetime import UTC, datetime

    disk_copy.write_text(
        json.dumps({"saved_at": datetime.now(UTC).isoformat(), "brief": {"old": True}}),
        encoding="utf-8",
    )
    builds = _counting_builder(monkeypatch, delay=0.4)
    assert cockpit.restore_from_disk() is True
    cockpit.warm()
    time.sleep(0.05)
    started = time.monotonic()
    assert cockpit.get_cockpit_state() == {"old": True}
    assert time.monotonic() - started < 0.2, "ilk ekran ısıtma derlemesini beklememeli"

    deadline = time.monotonic() + 5
    while cockpit._BRIEF_REFRESHING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert cockpit.get_cockpit_state() == {"n": 1}
    assert len(builds) == 1
    assert cockpit._RESTORED is False
    saved = json.loads(disk_copy.read_text(encoding="utf-8"))
    assert saved["brief"] == {"n": 1}


@pytest.mark.parametrize(
    "content",
    [
        "{bozuk",
        '{"saved_at": "2026-01-01T00:00:00+00:00", "brief": {"old": true}}',
        '{"brief": {"old": true}}',
        "OLD",
    ],
)
def test_old_or_corrupt_disk_copy_is_ignored(disk_copy, monkeypatch, content):
    import json
    from datetime import UTC, datetime, timedelta

    if content == "OLD":
        saved = datetime.now(UTC) - timedelta(hours=7)
        content = json.dumps({"saved_at": saved.isoformat(), "brief": {"old": True}})
    disk_copy.write_text(content, encoding="utf-8")
    assert cockpit.restore_from_disk() is False
    assert cockpit._BRIEF_CACHE is None
    assert cockpit._RESTORED is False


def test_missing_disk_copy_keeps_cold_start_behaviour(disk_copy, monkeypatch):
    builds = _counting_builder(monkeypatch, delay=0.0)
    assert cockpit.restore_from_disk() is False
    assert cockpit.get_cockpit_state() == {"n": 1}
    assert len(builds) == 1


def test_restore_never_overwrites_a_built_cache(disk_copy, monkeypatch):
    import json
    from datetime import UTC, datetime

    disk_copy.write_text(
        json.dumps({"saved_at": datetime.now(UTC).isoformat(), "brief": {"old": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cockpit, "_BRIEF_CACHE", (time.monotonic(), {"fresh": True}))
    assert cockpit.restore_from_disk() is False
    assert cockpit.get_cockpit_state() == {"fresh": True}


def test_disk_copy_written_at_most_once_a_minute(disk_copy, monkeypatch):
    import json

    builds = _counting_builder(monkeypatch, delay=0.0)
    cockpit._build_and_store()
    cockpit._build_and_store()
    assert len(builds) == 2
    assert json.loads(disk_copy.read_text(encoding="utf-8"))["brief"] == {"n": 1}


def test_supervisor_restores_before_api_listens(monkeypatch):
    import asyncio

    from apps.supervisor import main as sup

    order: list[str] = []
    monkeypatch.setenv("RUN_WORKERS", "false")
    monkeypatch.setattr(cockpit, "restore_from_disk", lambda: order.append("restore"))

    async def fake_warm(server, wait_tick_sec, timeout=120.0):
        order.append("warm")

    class FakeServer:
        def __init__(self, config):
            self.started = False

        async def serve(self):
            order.append("serve")

    import uvicorn

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(sup, "_warm_cockpit", fake_warm)
    asyncio.run(sup._serve())
    assert order.index("restore") < order.index("serve")
