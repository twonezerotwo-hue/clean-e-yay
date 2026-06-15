"""GET /api/v1/technical/insight/{asset_code} — multi-timeframe Fibonacci evidence.

Thin read-only HTTP layer over the technical provider. No paper-state mutation, no
trade actions, no broker. Fibonacci is technical EVIDENCE only — it never opens a
trade and never bypasses RiskGate.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.providers import technical as tech_provider
from packages.decision import agent_pipeline
from packages.paper import state as paper_state
from packages.risk import engine as risk_engine

router = APIRouter(tags=["technical"])

_MATRIX_SYMBOLS = DEFAULT_SYMBOLS[:4]


@router.get("/technical/insight/{asset_code}")
def get_technical_insight(asset_code: str) -> dict:
    return tech_provider.get_technical_insight(asset_code).model_dump()


@router.get("/technical/agent-matrix")
def get_agent_matrix() -> dict:
    """Read-only multi-TF agent pipeline (steps 1–6) as a per-symbol matrix.

    Thin HTTP layer — composition lives in `packages.decision.agent_pipeline`. The
    global RiskGate action is computed first and applied inside the pipeline; the
    per-trade cost + R:R gate is final. No paper-state mutation, no trade actions,
    no broker.
    """
    snap = get_cached_snapshot()
    ps = paper_state.load()
    risk = risk_engine.evaluate(
        risk_engine.RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )
    )
    views = agent_pipeline.build_agent_matrix(_MATRIX_SYMBOLS, risk_action=risk.action)
    return agent_pipeline.matrix_viewmodel(views, risk_action=risk.action)
