"""GET /api/v1/cockpit/brief — UX1 Agent Operating Cockpit ViewModel.

Tek çağrıda ilk-ekran cockpit'i besler: AgentBrief (özet beyin) + DecisionTrace
(candidate→final karar izi). Yalnızca mevcut state'i okur ve sadeleştirir —
yeni karar / emir / live çağrı YOK. Karar zinciri (decide_matrix + matrix_view)
diğer endpoint'lerle aynıdır; bu router sadece özet üretir. PAPER_SAFE.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.agent.llm.world_report import build_world_brief
from packages.causal.engine import build_shadow
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.decision import paper_policy
from packages.decision.cockpit import agent_brief_view, decision_trace_view
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import state as paper_state
from packages.portfolio import build_portfolio_risk
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput
from packages.world_state.engine import build as build_world_state

router = APIRouter(tags=["cockpit"])


@router.get("/cockpit/brief")
def get_cockpit_brief() -> dict:
    snap = get_cached_snapshot()
    ps = paper_state.load()
    matrix_symbols = asset_registry.trade_symbols()
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )
    regime, risk, decisions = decide_matrix(
        matrix_symbols,
        snap,
        risk_in,
        open_positions=ps.open_positions,
        paper_exploration=paper_policy.enabled(),
    )
    view = matrix_view(regime, risk, decisions, snap, matrix_symbols)
    provenance = data_provenance(snap)
    halt_active = bool(halt_store.active_halts())
    world_state = build_world_state(snap)
    legacy_scores: dict[str, dict[str, object]] = {}
    conflict_inputs: dict[str, dict[str, object]] = {}
    for decision in decisions:
        key = f"{decision.symbol}|{decision.timeframe}"
        legacy_scores[key] = {
            "score": decision.consensus.score,
            "direction": decision.consensus.direction,
            "timeframe": decision.timeframe,
        }
        if decision.timeframe == "1d":
            legacy_scores[decision.symbol] = legacy_scores[key]
            conflict_inputs[decision.symbol] = {
                "dqs_status": "OK" if snap.quality.status == "OK" else "DEGRADED",
                "risk_gate_action": risk.action,
                "trigger_confirmed": bool(decision.actionable),
                "trade_economics_valid": None,
                "rr_context_unavailable": True,
                "setup_type": "SETUP" if decision.candidate_action != "hold" else "NO_TRADE",
                "historical_edge_strong_negative": ((decision.meta_gate_report or {}).get("verdict") == "AVOID") if decision.meta_gate_report else None,
                "size_multiplier": decision.size_multiplier,
                "alignment_status": "ALIGNED" if decision.consensus.confluence_aligned else "PARTIAL",
            }
    causal_shadow = build_shadow(
        world_state,
        matrix_symbols,
        technicals=snap.technicals_by_tf or snap.technicals,
        prices={quote.symbol: quote for quote in snap.prices},
        volatility=snap.volatility,
        legacy_scores=legacy_scores,
        conflict_inputs=conflict_inputs,
    )
    portfolio_risk = build_portfolio_risk(
        ps,
        impacts={impact.symbol: impact for impact in causal_shadow.impacts},
    )
    world_brief = build_world_brief(
        headlines=snap.headlines,
        world_state=world_state.to_dict(),
        causal_shadow=causal_shadow.to_dict(),
        portfolio_risk=portfolio_risk.to_dict(),
        risk_gate={"action": risk.action, "reason": risk.reason},
        dqs={"status": snap.quality.status, "score": snap.quality.score},
    )
    return {
        "generated_at": view["generated_at"],
        "mode": provenance,
        "agent_brief": agent_brief_view(
            view, snap, ps, provenance, halt_active=halt_active
        ),
        "decision_trace": decision_trace_view(view, snap),
        "world_state": world_state.to_dict(),
        "world_brief": world_brief,
        "causal_shadow": causal_shadow.to_dict(),
        "portfolio_risk": portfolio_risk.to_dict(),
    }
