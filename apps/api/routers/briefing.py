"""GET /api/v1/agent/briefing — deterministik raporcu agent.

LLM yok. Mevcut state'i tarayıp başlık başlık özet döner.
UI panel'i bunu polll'lar (10-15s) + SSE tick.complete'te yeniler.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["agent"])


@router.get("/agent/briefing")
def get_briefing() -> dict:
    # Keep legacy consumers on the same authoritative cache as Cockpit.  The
    # old endpoint remains available, but it must not calculate a second
    # snapshot/position cycle and then contradict the dashboard.
    from apps.api.routers.cockpit import get_cockpit_brief

    cockpit = get_cockpit_brief()
    agent = cockpit.get("agent_brief") or {}
    return {
        "generated_at": cockpit.get("generated_at"),
        "snapshot_id": cockpit.get("snapshot_id"),
        "snapshot_generated_at": cockpit.get("snapshot_generated_at"),
        "paper_state_revision": cockpit.get("paper_state_revision"),
        "open_positions": [
            {
                "id": position.get("id"),
                "symbol": position.get("symbol"),
                "side": position.get("side"),
                "timeframe": position.get("timeframe"),
                "size_usd": position.get("size_usd"),
                "unrealized_pnl_usd": position.get("unrealized_pnl_usd"),
            }
            for position in (cockpit.get("paper_state") or {}).get("open_positions", [])
        ],
        "regime_label": agent.get("regime"),
        "stale": bool((cockpit.get("engine") or {}).get("stale", False)),
        "executive": cockpit.get("executive"),
        "engine": cockpit.get("engine"),
        "dqs": agent.get("dqs"),
        # Preserve the legacy AgentBriefing contract while sourcing every row
        # from the same cockpit evidence envelope.
        "headlines": [
            {
                "tone": (
                    "warn"
                    if headline.get("sentiment") == "bearish"
                    else "ok"
                    if headline.get("sentiment") == "bullish"
                    else "info"
                ),
                "category": headline.get("source") or "news",
                "title": headline.get("title_tr") or headline.get("title") or "",
                "detail": headline.get("region"),
            }
            for headline in cockpit.get("headlines") or []
        ],
    }
