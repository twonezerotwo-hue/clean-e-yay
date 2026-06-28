"""Supervisor entry point — uvicorn API + tick + learning, tek loop.

    python -m apps.supervisor

Ortam değişkenleri:
    API_HOST              (default 0.0.0.0)
    API_PORT              (default 9000)
    LEARNING_INTERVAL_SEC (default 300)
    GOVERNOR_INTERVAL_SEC (default 900)
    RUN_WORKERS           (default true) — false ise sadece API
    RUN_GOVERNOR          (default true) — false ise governor döngüsü kapalı

Mimari not: arka plan döngülerinin sahibi BURASIDIR, apps/api değil. Bu
sayede apps/api ince HTTP katmanı olarak kalır (architecture guard geçer),
ama kullanıcı hâlâ tek komutla 7/24 agent + API alır.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

_log = logging.getLogger("apps.supervisor")


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


async def _learning_loop(stop: asyncio.Event, interval: int) -> None:
    """learning_worker.run_once'ı periyodik döngüye sar (one-shot → daemon)."""
    from apps.learning_worker.main import run_once as learning_run_once

    _log.info("learning loop started, interval=%ds", interval)
    while not stop.is_set():
        try:
            await asyncio.to_thread(learning_run_once)
        except Exception:
            _log.exception("learning run_once failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    _log.info("learning loop stopped")


async def _governor_loop(stop: asyncio.Event, interval: int) -> None:
    """governor_worker.run_once'ı periyodik döngüye sar (observe-only, read-only).

    learning_loop ile aynı desen. governor trade açmaz / config değiştirmez —
    yalnızca görev üretir + read-only rapor toplar. Hata izole (worker patlamaz)."""
    from apps.governor_worker.main import run_once as governor_run_once

    _log.info("governor loop started, interval=%ds", interval)
    while not stop.is_set():
        try:
            await asyncio.to_thread(governor_run_once)
        except Exception:
            _log.exception("governor run_once failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    _log.info("governor loop stopped")


async def _serve() -> None:
    import uvicorn

    from apps.api.main import app

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "9000"))

    config = uvicorn.Config(app, host=host, port=port, log_level="info", lifespan="on")
    server = uvicorn.Server(config)

    stop = asyncio.Event()
    tasks: list[asyncio.Task] = []

    if _env_truthy("RUN_WORKERS", "true"):
        # tick_worker kendi sinyal handler'larını kurmasın — supervisor/uvicorn yönetir.
        os.environ.setdefault("TICK_SKIP_SIGNAL_HANDLERS", "1")
        from apps.tick_worker.main import _STOP as tick_stop
        from apps.tick_worker.main import run as tick_run

        interval = int(os.environ.get("LEARNING_INTERVAL_SEC", "300"))
        tasks = [
            asyncio.create_task(tick_run(), name="tick_worker"),
            asyncio.create_task(_learning_loop(stop, interval), name="learning_loop"),
        ]
        if _env_truthy("RUN_GOVERNOR", "true"):
            gov_interval = int(os.environ.get("GOVERNOR_INTERVAL_SEC", "900"))
            tasks.append(
                asyncio.create_task(
                    _governor_loop(stop, gov_interval), name="governor_loop"
                )
            )
            _log.info("agent ON — tick + learning + governor workers running alongside API")
        else:
            _log.info("agent ON — tick + learning workers running alongside API")
    else:
        tick_stop = None
        _log.info("agent OFF (RUN_WORKERS=false) — API only")

    try:
        # uvicorn.Server.serve() SIGINT/SIGTERM'i kendi yakalar; çıkışta
        # worker'ları durdururuz.
        await server.serve()
    finally:
        stop.set()
        if tick_stop is not None:
            tick_stop.set()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await asyncio.wait_for(t, timeout=5.0)
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
