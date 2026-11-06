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

    warmed: list[float] = []
    monkeypatch.setattr(cockpit, "warm", lambda: warmed.append(time.monotonic()))
    server = SimpleNamespace(started=False)

    async def scenario() -> float:
        task = asyncio.create_task(sup._warm_cockpit(server, timeout=5))
        await asyncio.sleep(0.2)
        assert warmed == [], "API dinlemeden ısıtma başlamaz"
        server.started = True
        started_at = time.monotonic()
        await asyncio.wait_for(task, timeout=3)
        return started_at

    started_at = asyncio.run(scenario())
    assert len(warmed) == 1 and warmed[0] >= started_at
