"""Clean E-yAy API — sözleşme tarafından yönetilen ince HTTP katmanı.

Tüm karar mantığı packages/ altındaki paketlerdedir. Eklenen her endpoint
önce contracts/openapi.yaml içinde tanımlanmalıdır.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path


def _load_dotenv() -> None:
    """Repo root .env'i yükle — sadece set edilmemiş değişkenler.

    Bağımlılık yok (python-dotenv değil). Format: KEY=VALUE, # comment, boş
    satır. Quote/escape yok. Mevcut shell env'i override ETMEZ.
    """
    p = Path(__file__).resolve().parent.parent.parent / ".env"
    if not p.exists():
        return
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


_load_dotenv()

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
    analysis,
    briefing,
    chat,
    cockpit,
    dashboard_state,
    data,
    decision,
    health,
    learning,
    liquidity,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # apps/api ince HTTP katmanı: arka plan döngüsü YOK (architecture guard).
    # Tick + learning worker'ları ayrı process'lerdir; tek komutla birlikte
    # çalıştırmak için `python -m apps.supervisor` kullan (api + worker'ları
    # tek event-loop'ta yönetir, apps/api'yi kirletmeden).
    app.state.started_at = _START_TS
    yield


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
    app.include_router(liquidity.router, prefix=prefix)
    app.include_router(analysis.router, prefix=prefix)
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
