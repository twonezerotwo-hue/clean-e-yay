"""GET/POST /api/v1/learning/rebalance/*

- GET  proposal          → bekleyen + history
- POST propose           → trainer'ı koş, proposal yaz (idempotent: yeni proposal eskiyi supersede eder)
- POST approve           → yeni weights_v1.x.yaml + manifest
- POST reject            → proposal'ı sil

Politika: Owner approval olmadan ağırlık değişmez. PAPER_SAFE.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.data.registry.loader import active_weights_version
from packages.learning import auto_weight_trainer as trainer
from packages.learning import rebalance_store as store
from packages.learning import weight_autoapply_store

router = APIRouter(tags=["learning"])


class RegimeBody(BaseModel):
    regime: str = "NEUTRAL"


class ApproveBody(BaseModel):
    approved_by: str = "owner"


class RejectBody(BaseModel):
    reason: str = "owner_reject"


@router.get("/learning/rebalance/proposal")
def get_proposal() -> dict:
    # G3 — otomatik-uygulama görünürlüğü (conscious layer): izlenen aktif apply +
    # ledger (AUTO_APPLIED/CONFIRMED/ROLLED_BACK). Owner, ağırlıkların ne zaman
    # kendi başına değişip geri alındığını cockpit'te görür.
    return {
        "active_version": active_weights_version(),
        "current": store.get_pending(),
        "history": store.history(20),
        "auto_apply": {
            "active": weight_autoapply_store.get_active(),
            "ledger": weight_autoapply_store.history(20),
        },
    }


@router.post("/learning/rebalance/propose")
def post_propose(body: RegimeBody | None = None) -> dict:
    regime = (body.regime if body else "NEUTRAL").upper()
    result = trainer.train(regime=regime)
    if isinstance(result, dict):
        return {"status": result.get("status", "SKIPPED"), "detail": result}
    proposal = trainer.proposal_to_dict(result)
    saved = store.set_pending(proposal)
    if saved.get("status") == "NO_CHANGE":
        return {"status": "NO_CHANGE", "detail": saved}
    return {"status": "PENDING", "proposal": saved}


@router.post("/learning/rebalance/approve")
def post_approve(body: ApproveBody | None = None) -> dict:
    approved_by = body.approved_by if body else "owner"
    res = store.approve_current(approved_by=approved_by)
    if res is None:
        raise HTTPException(status_code=404, detail="No pending proposal")
    return {"status": "APPROVED", "proposal": res}


@router.post("/learning/rebalance/reject")
def post_reject(body: RejectBody | None = None) -> dict:
    reason = body.reason if body else "owner_reject"
    res = store.reject_current(reason=reason)
    if res is None:
        raise HTTPException(status_code=404, detail="No pending proposal")
    return {"status": "REJECTED", "proposal": res}
