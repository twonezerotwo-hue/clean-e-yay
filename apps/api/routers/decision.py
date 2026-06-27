"""GET /api/v1/decision/matrix — T2 (symbol × timeframe) karar matrisi.

Frontend hesap yapmaz: hücre rozetleri (ACTIONABLE / NOT_ACTIONABLE /
SUSPENDED), candidate vs final ayrımı ve blocked_by backend ViewModel'inde
gelir. RiskGate global: KILL_SWITCH / halt / DQS BLOCKED → tüm hücreler
SUSPENDED.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.data.registry import assets as asset_registry
from packages.decision import shadow
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import state as paper_state
from packages.risk.engine import RiskInput

router = APIRouter(tags=["decision"])


@router.get("/decision/matrix")
def get_decision_matrix() -> dict:
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
    view["mode"] = data_provenance(snap)
    return view


@router.get("/decision/shadow")
def get_shadow_comparison() -> dict:
    """Step 9 — latest live-vs-shadow comparison (observe-only).

    Thin read layer over the shadow log the tick_worker writes; it never runs the
    pipeline, never touches paper, and `affected_paper` is always false (Phase A).
    """
    return shadow.latest_viewmodel()
