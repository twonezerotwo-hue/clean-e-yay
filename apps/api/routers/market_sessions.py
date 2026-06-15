"""GET /api/v1/market-sessions/current — open/closing/opening market statuses.
GET /api/v1/market-sessions/asset/{asset_code} — per-asset session context + gate.

Thin read-only HTTP layer over packages/market_sessions. No business logic here,
no paper state mutation, no trade actions, no broker — PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter

from packages import market_sessions
from packages.market_sessions.models import MarketSessionDecisionInput

router = APIRouter(tags=["market-sessions"])


@router.get("/market-sessions/current")
def get_market_sessions_current() -> dict:
    now = datetime.now(UTC)
    statuses = market_sessions.all_market_statuses(now)
    diagnostics = sorted({d for s in statuses for d in s.diagnostics})
    return {
        "generated_at": now.isoformat(),
        "markets": [asdict(s) for s in statuses],
        "diagnostics": diagnostics,
        "paper_safe": True,
        "no_execution": True,
    }


@router.get("/market-sessions/asset/{asset_code}")
def get_market_session_asset(asset_code: str) -> dict:
    now = datetime.now(UTC)
    cfg = market_sessions.load_config()
    ctx = market_sessions.asset_context(asset_code, now, cfg)
    decision = market_sessions.evaluate(
        MarketSessionDecisionInput(asset_code=asset_code, now_utc=now), cfg
    )
    return {
        "generated_at": now.isoformat(),
        "asset_code": ctx.asset_code,
        "asset_context": asdict(ctx),
        "decision": asdict(decision),
        "diagnostics": sorted(set(ctx.diagnostics) | set(decision.diagnostics)),
        "paper_safe": True,
        "no_execution": True,
    }
