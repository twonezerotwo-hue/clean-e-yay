"""GET /api/v1/agent/briefing — deterministik raporcu agent.

LLM yok. Mevcut state'i tarayıp başlık başlık özet döner.
UI panel'i bunu polll'lar (10-15s) + SSE tick.complete'te yeniler.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.agent.briefing import build

router = APIRouter(tags=["agent"])


@router.get("/agent/briefing")
def get_briefing() -> dict:
    return build()
