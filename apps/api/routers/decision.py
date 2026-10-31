"""GET /api/v1/decision/matrix — T2 (symbol × timeframe) karar matrisi.

Frontend hesap yapmaz: hücre rozetleri (ACTIONABLE / NOT_ACTIONABLE /
SUSPENDED), candidate vs final ayrımı ve blocked_by backend ViewModel'inde
gelir. RiskGate global: KILL_SWITCH / halt / DQS BLOCKED → tüm hücreler
SUSPENDED.
"""
from __future__ import annotations

from fastapi import APIRouter

from packages.data.provenance import data_provenance
from packages.decision import read_model, shadow

router = APIRouter(tags=["decision"])


@router.get("/decision/matrix")
def get_decision_matrix() -> dict:
    dv = read_model.current()
    snap, ps = dv.snap, dv.ps
    view = dv.matrix()
    view["mode"] = data_provenance(snap)
    # Version envelope: consumers can reject a matrix that belongs to a
    # different market snapshot or paper-state revision instead of mixing it
    # with newer prices/positions.
    view["snapshot_id"] = snap.snapshot_id
    view["snapshot_generated_at"] = snap.generated_at.isoformat()
    view["paper_state_revision"] = ps.revision
    return view


@router.get("/decision/shadow")
def get_shadow_comparison() -> dict:
    """Step 9 — latest live-vs-shadow comparison (observe-only).

    Thin read layer over the shadow log the tick_worker writes; it never runs the
    pipeline, never touches paper, and `affected_paper` is always false (Phase A).
    """
    return shadow.latest_viewmodel()
