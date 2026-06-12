"""GET /api/v1/decision/matrix — T2 (symbol × timeframe) karar matrisi.

Frontend hesap yapmaz: hücre rozetleri (ACTIONABLE / NOT_ACTIONABLE /
SUSPENDED), candidate vs final ayrımı ve blocked_by backend ViewModel'inde
gelir. RiskGate global: KILL_SWITCH / halt / DQS BLOCKED → tüm hücreler
SUSPENDED.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.provenance import data_provenance
from packages.decision.engine import decide_matrix, matrix_view
from packages.paper import state as paper_state
from packages.risk.engine import RiskInput

router = APIRouter(tags=["decision"])

MATRIX_SYMBOLS = DEFAULT_SYMBOLS[:4]


@router.get("/decision/matrix")
def get_decision_matrix() -> dict:
    snap = get_cached_snapshot()
    ps = paper_state.load()
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )
    regime, risk, decisions = decide_matrix(
        MATRIX_SYMBOLS, snap, risk_in, open_positions=ps.open_positions
    )
    view = matrix_view(regime, risk, decisions, snap, MATRIX_SYMBOLS)
    view["mode"] = data_provenance(snap)
    return view
