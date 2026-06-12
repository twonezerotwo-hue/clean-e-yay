"""Clean E-yAy API — sözleşme tarafından yönetilen ince HTTP katmanı.

Tüm karar mantığı packages/ altındaki paketlerdedir. Eklenen her endpoint
önce contracts/openapi.yaml içinde tanımlanmalıdır.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    ai_report,
    chat,
    dashboard_state,
    data,
    decision,
    health,
    learning,
    paper_trading,
    rebalance,
    regime_report,
    risk,
)

_START_TS = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = _START_TS
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clean E-yAy API",
        version="2.0.0",
        lifespan=lifespan,
    )
    # Local dev: DEV_CORS=true → tüm origin'ler. Aksi halde whitelist:
    # 3000/3001 portları + env'den ek origin (CORS_EXTRA_ORIGINS, virgülle).
    extra = os.environ.get("CORS_EXTRA_ORIGINS", "").strip()
    extra_list = [o.strip() for o in extra.split(",") if o.strip()]
    if os.environ.get("DEV_CORS", "").lower() == "true":
        allow_origins = ["*"]
    else:
        allow_origins = [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3001",
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
    app.include_router(learning.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    app.include_router(decision.router, prefix=prefix)
    app.include_router(rebalance.router, prefix=prefix)
    app.include_router(risk.router, prefix=prefix)
    return app


app = create_app()
