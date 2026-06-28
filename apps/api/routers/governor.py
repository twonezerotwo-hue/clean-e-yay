"""Governor — self-managing katman API'si (Part 1: öneri defteri + özet).

GET  /api/v1/governor/report                       → read-only özet (ne öğrendi/
                                                      buldu/öneriyor/onay bekliyor)
GET  /api/v1/governor/proposals                    → öneri defteri (pending+history)
POST /api/v1/governor/proposals                    → yeni öneri kaydet (PENDING)
POST /api/v1/governor/proposals/{id}/approve       → owner kararı: APPROVED
POST /api/v1/governor/proposals/{id}/reject        → owner kararı: REJECTED

DEĞİŞMEZ: approve canlı config'i (weights/thresholds/risk/mode) DEĞİŞTİRMEZ —
yalnızca defter kaydını günceller. Gerçek uygulama mevcut owner-gated yollardan
yapılır (bkz. packages/governor/proposals modül docstring'i). PAPER_SAFE /
NO_EXECUTION: trade açmaz, RiskGate bypass etmez.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from packages.governor import proposals as proposals_store
from packages.governor import report as governor_report
from packages.governor import tasks as task_queue

router = APIRouter(tags=["governor"])


@router.get("/governor/report")
def get_governor_report() -> dict:
    """Read-only governor özeti. Hiçbir alt kaynak raporu düşürmez (best-effort)."""
    return governor_report.build_report()


@router.get("/governor/proposals")
def get_governor_proposals() -> dict:
    """Öneri defteri görünümü: bekleyen + son geçmiş + tip sayaçları."""
    return proposals_store.summary_viewmodel()


@router.post("/governor/proposals")
def post_governor_proposal(payload: dict) -> dict:
    """Yeni öneri kaydet (sanitize edilir; bilinmeyen tip reddedilir). Aynı
    (tip, requested_change) PENDING zaten varsa onu döner (çift kayıt yok)."""
    proposal = proposals_store.submit(payload or {})
    if proposal is None:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_proposal",
                "reason": "geçersiz proposal_type veya boş title",
                "allowed_types": list(proposals_store.PROPOSAL_TYPES),
            },
        )
    return {"submitted": True, "proposal": proposal}


@router.post("/governor/proposals/{proposal_id}/approve")
def post_approve_proposal(proposal_id: str) -> dict:
    """Owner kararı: APPROVED. Canlı config'e DOKUNMAZ (yalnızca kayıt)."""
    rec = proposals_store.approve(proposal_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "proposal_id": proposal_id},
        )
    return {"approved": True, "proposal": rec}


@router.post("/governor/proposals/{proposal_id}/reject")
def post_reject_proposal(proposal_id: str, payload: dict | None = None) -> dict:
    """Owner kararı: REJECTED (opsiyonel `reason`)."""
    reason = (payload or {}).get("reason") or "owner_reject"
    rec = proposals_store.reject(proposal_id, reason=str(reason)[:200])
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "proposal_id": proposal_id},
        )
    return {"rejected": True, "proposal": rec}


# ── Görev Kuyruğu (observe-only) ─────────────────────────────────────────────


@router.get("/governor/tasks")
def get_governor_tasks() -> dict:
    """Görev kuyruğu görünümü: bekleyen (öncelikli) + son geçmiş + sayaçlar."""
    return task_queue.summary_viewmodel()


@router.post("/governor/tasks")
def post_governor_task(payload: dict) -> dict:
    """Manuel görev ekle (sanitize; bilinmeyen tip reddedilir). `can_change_policy`
    girdiden okunmaz — daima False."""
    p = payload or {}
    task = task_queue.enqueue(
        str(p.get("task_type") or ""),
        subject=str(p.get("subject") or ""),
        params=p.get("params") if isinstance(p.get("params"), dict) else {},
        priority=p.get("priority"),
        source=str(p.get("source") or "owner"),
    )
    if task is None:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_task",
                "allowed_types": list(task_queue.TASK_TYPES),
            },
        )
    return {"enqueued": True, "task": task}


@router.post("/governor/tasks/generate")
def post_generate_tasks() -> dict:
    """Mevcut store'lara bakıp gereken observe-only görevleri üret (dedup'lu)."""
    created = task_queue.generate()
    return {"generated": len(created), "tasks": created}


@router.post("/governor/tasks/{task_id}/run")
def post_run_task(task_id: str) -> dict:
    """Görevi koş → read-only rapor üret. Bulunamazsa 404."""
    rec = task_queue.execute(task_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "task_id": task_id},
        )
    return {"executed": True, "task": rec}
