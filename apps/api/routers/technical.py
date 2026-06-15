"""GET /api/v1/technical/insight/{asset_code} — multi-timeframe Fibonacci evidence.

Thin read-only HTTP layer over the technical provider. No paper-state mutation, no
trade actions, no broker. Fibonacci is technical EVIDENCE only — it never opens a
trade and never bypasses RiskGate.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.providers import technical as tech_provider

router = APIRouter(tags=["technical"])


@router.get("/technical/insight/{asset_code}")
def get_technical_insight(asset_code: str) -> dict:
    return tech_provider.get_technical_insight(asset_code).model_dump()
