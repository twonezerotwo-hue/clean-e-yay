"""Health router — uptime + sürüm. Tek bağımlılık: zaman."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health(request: Request) -> dict:
    started_at = getattr(request.app.state, "started_at", time.monotonic())
    return {
        "status": "ok",
        "version": "2.0.0",
        "uptime_sec": round(time.monotonic() - started_at, 2),
    }
