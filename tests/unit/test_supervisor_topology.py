"""Tek çalışma şekli (owner kararı 2026-10-02): supervisor her yerde.

Supervisor'ın tick'i event loop'u bloke etmemeli (API donmasın) ve tick
tekil-süreç kilidine uymalı (eski ayrı tick süreci canlıyken çift yazar yok).
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from apps.supervisor import main as sup
from apps.tick_worker import main as tick


@pytest.fixture
def tick_lock(tmp_path, monkeypatch):
    path = tmp_path / "tick_worker.lock"
    monkeypatch.setattr(tick, "LOCK_PATH", path)
    monkeypatch.setattr(tick, "_LOCK_FD", None)
    monkeypatch.delenv("TICK_WORKER_DISABLE_LOCK", raising=False)
    return path


def test_tick_does_not_block_event_loop(tick_lock, monkeypatch):
    calls = []

    async def slow_sync_tick():  # gerçek run_once gibi: async adlı, içi senkron
        calls.append(time.monotonic())
        time.sleep(0.6)

    monkeypatch.setattr(tick, "run_once", slow_sync_tick)

    async def scenario():
        stop = asyncio.Event()
        loop_task = asyncio.create_task(sup._tick_loop(stop, interval=60))
        gaps, last = [], time.monotonic()
        for _ in range(20):  # ~1 sn boyunca loop'un nabzını ölç
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now
        stop.set()
        await asyncio.wait_for(loop_task, timeout=5)
        return gaps

    gaps = asyncio.run(scenario())
    assert calls, "tick hiç koşmadı"
    assert max(gaps) < 0.3, f"event loop bloke oldu: en uzun boşluk {max(gaps):.2f}s"
    assert not tick_lock.exists(), "durunca kilit bırakılmalı"


def test_tick_skipped_while_other_tick_process_alive(tick_lock, monkeypatch):
    # Kilit canlı başka bir sürece ait (burada: test sürecinin kendisi).
    tick_lock.write_text(f"{os.getpid()}|2026-10-02T00:00:00+00:00", encoding="utf-8")
    ran = []

    async def fake_tick():
        ran.append(1)

    monkeypatch.setattr(tick, "run_once", fake_tick)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(sup._tick_loop(stop, interval=60))
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
    assert ran == []
    assert tick_lock.exists(), "başkasının kilidine dokunulmaz"


def test_stale_lock_is_taken_over(tick_lock, monkeypatch):
    tick_lock.write_text("0|2026-10-02T00:00:00+00:00", encoding="utf-8")  # ölü pid
    ran = []

    async def fake_tick():
        ran.append(1)

    monkeypatch.setattr(tick, "run_once", fake_tick)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(sup._tick_loop(stop, interval=60))
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
    assert ran == [1]
    assert not tick_lock.exists()
