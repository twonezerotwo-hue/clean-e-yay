"""GET /api/v1/dashboard/state"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from packages.agent.personas import build_votes
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.paper import state as paper_state
from packages.paper.lifecycle import max_drawdown_pct
from packages.regime.classifier import classify
from packages.risk.engine import RiskInput, evaluate

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/state")
def get_dashboard_state() -> dict:
    snap = get_cached_snapshot()
    regime = classify(snap)
    ps = paper_state.load()
    risk = evaluate(
        RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )
    )
    # Top sembolün consensus'üyle agent oyu üret
    top_cons = build_consensus(DEFAULT_SYMBOLS[0], snap, regime)
    votes, quorum = build_votes(top_cons, regime, risk)
    now_iso = datetime.now(UTC).isoformat()
    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "dqs_score": snap.quality.score,
            "fallback_used": snap.quality.fallback_used,
        },
        "risk_gate": {
            "action": risk.action,
            "reason": risk.reason,
            "evidence": risk.evidence,
        },
        "agent_votes": [
            {
                "persona": v.persona,
                "direction": v.direction,
                "confidence": v.confidence,
                "narrative": v.narrative,
            }
            for v in votes
        ],
        "quorum_reached": quorum,
        "module_health": {
            "data": {"status": "ok", "last_success_at": now_iso, "notes": "mock providers"},
            "regime": {"status": "ok", "last_success_at": now_iso},
            "consensus": {"status": "ok", "last_success_at": now_iso},
            "paper_trading": {
                "status": "ok",
                "last_success_at": now_iso,
                "notes": f"equity {ps.equity_usd:.0f}, DD {max_drawdown_pct(ps):.1%}",
            },
        },
        "warnings": snap.warnings,
    }
