"""Clean E-yAy API — sözleşme tarafından yönetilen ince HTTP katmanı.

Tüm karar mantığı packages/ altındaki paketlerdedir. Eklenen her endpoint
önce contracts/openapi.yaml içinde tanımlanmalıdır.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

# Windows-only: ProactorEventLoop (Python 3.8+ default on win32) crashes the
# whole API process when it sees malformed accept events — observed in
# practice under Cloudflare Tunnel / Worker reverse-proxy traffic with
# "OSError: [WinError 64] Belirtilen ağ adı artık geçersiz" bubbling up
# out of the accept coroutine and never being retrieved.
# SelectorEventLoop on Windows tolerates these silently and is fine for
# uvicorn workloads (no subprocess on the event loop, < 64 sockets).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    ai_report,
    briefing,
    chat,
    cockpit,
    dashboard_state,
    data,
    decision,
    health,
    learning,
    market_sessions,
    paper_trading,
    rebalance,
    regime_report,
    replay,
    risk,
    stream,
    system,
    technical,
)

_START_TS = time.monotonic()
_log = logging.getLogger("apps.api.agent")


def _env_truthy(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


async def _learning_loop(stop: asyncio.Event, interval: int) -> None:
    """Wrap learning_worker.run_once in a periodic loop (one-shot script → daemon)."""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = _START_TS
    app.state.agent_tasks = []
    app.state.agent_stop = asyncio.Event()

    if _env_truthy("EMBEDDED_WORKERS", "true"):
        # Tick worker (decisions, paper lifecycle, snapshots) — async loop.
        from apps.tick_worker.main import run as tick_run

        # Tick worker installs its own SIGTERM/SIGINT handlers when run as a
        # standalone process. Skip that here — uvicorn owns the signals.
        os.environ.setdefault("TICK_SKIP_SIGNAL_HANDLERS", "1")

        learning_interval = int(os.environ.get("LEARNING_INTERVAL_SEC", "300"))

        app.state.agent_tasks = [
            asyncio.create_task(tick_run(), name="tick_worker"),
            asyncio.create_task(
                _learning_loop(app.state.agent_stop, learning_interval),
                name="learning_loop",
            ),
        ]
        _log.info("embedded agent ON — tick + learning workers running in-process")
    else:
        _log.info("embedded agent OFF (EMBEDDED_WORKERS=false)")

    try:
        yield
    finally:
        app.state.agent_stop.set()
        # Signal tick_worker's own STOP event too.
        try:
            from apps.tick_worker.main import _STOP as _tick_stop

            _tick_stop.set()
        except Exception:
            pass
        for task in app.state.agent_tasks:
            task.cancel()
        for task in app.state.agent_tasks:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clean E-yAy API",
        version="2.0.0",
        lifespan=lifespan,
    )
    # Local dev: DEV_CORS=true → tüm origin'ler. Aksi halde whitelist:
    # 4000 (web) portu + env'den ek origin (CORS_EXTRA_ORIGINS, virgülle).
    extra = os.environ.get("CORS_EXTRA_ORIGINS", "").strip()
    extra_list = [o.strip() for o in extra.split(",") if o.strip()]
    if os.environ.get("DEV_CORS", "").lower() == "true":
        allow_origins = ["*"]
    else:
        allow_origins = [
            "http://127.0.0.1:4000",
            "http://localhost:4000",
            *extra_list,
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(regime_report.router, prefix=prefix)
    app.include_router(dashboard_state.router, prefix=prefix)
    app.include_router(ai_report.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(paper_trading.router, prefix=prefix)
    app.include_router(market_sessions.router, prefix=prefix)
    app.include_router(learning.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    app.include_router(technical.router, prefix=prefix)
    app.include_router(decision.router, prefix=prefix)
    app.include_router(cockpit.router, prefix=prefix)
    app.include_router(rebalance.router, prefix=prefix)
    app.include_router(risk.router, prefix=prefix)
    app.include_router(replay.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    app.include_router(stream.router, prefix=prefix)
    app.include_router(briefing.router, prefix=prefix)
    return app


app = create_app()
