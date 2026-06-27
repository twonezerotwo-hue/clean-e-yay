"""GET /api/v1/cockpit/brief — UX1 Agent Operating Cockpit ViewModel.

Tek çağrıda ilk-ekran cockpit'i besler: AgentBrief (özet beyin) + DecisionTrace
(candidate→final karar izi). Yalnızca mevcut state'i okur ve sadeleştirir —
yeni karar / emir / live çağrı YOK. Karar zinciri (decide_matrix + matrix_view)
diğer endpoint'lerle aynıdır; bu router sadece özet üretir. PAPER_SAFE.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.decision.cockpit import agent_brief_view, decision_trace_view
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import state as paper_state
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

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
        matrix_symbols, snap, risk_in, open_positions=ps.open_positions
    )
    view = matrix_view(regime, risk, decisions, snap, matrix_symbols)
    provenance = data_provenance(snap)
    halt_active = bool(halt_store.active_halts())
    return {
        "generated_at": view["generated_at"],
        "mode": provenance,
        "agent_brief": agent_brief_view(
            view, snap, ps, provenance, halt_active=halt_active
        ),
        "decision_trace": decision_trace_view(view, snap),
    }
