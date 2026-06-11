"""Clean E-yAy API — sözleşme tarafından yönetilen ince HTTP katmanı.

Bu modül HTTP yönlendiriciden başka iş yapmaz. Tüm karar mantığı
packages/ altındaki paketlerdedir. Eklenen her endpoint önce
`contracts/openapi.yaml` içinde tanımlanmalıdır.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import health


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
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
