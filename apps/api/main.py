"""Clean E-yAy API — sözleşme tarafından yönetilen ince HTTP katmanı.

Tüm karar mantığı packages/ altındaki paketlerdedir. Eklenen her endpoint
önce contracts/openapi.yaml içinde tanımlanmalıdır.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    ai_report,
    dashboard_state,
    data,
    health,
    learning,
    paper_trading,
    regime_report,
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(regime_report.router, prefix=prefix)
    app.include_router(dashboard_state.router, prefix=prefix)
    app.include_router(ai_report.router, prefix=prefix)
    app.include_router(paper_trading.router, prefix=prefix)
    app.include_router(learning.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    return app


app = create_app()
