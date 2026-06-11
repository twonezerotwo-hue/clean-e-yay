"""GET /api/v1/ai-report/current"""
from __future__ import annotations

from fastapi import APIRouter

from packages.agent.narrative import build_narrative
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.data.provenance import data_provenance, decision_disclaimer
from packages.regime.classifier import classify

router = APIRouter(tags=["ai"])


@router.get("/ai-report/current")
def get_ai_report_current() -> dict:
    snap = get_cached_snapshot()
    regime = classify(snap)
    cons_list = [build_consensus(s, snap, regime) for s in DEFAULT_SYMBOLS[:6]]
    verdict, narrative, key_signals = build_narrative(cons_list, regime)
    prov = data_provenance(snap)
    disclaimer = decision_disclaimer(snap)
    if disclaimer is not None:
        narrative = f"{disclaimer}\n\n{narrative}"
        key_signals = [disclaimer, *key_signals]
    return {
        "meta": {
            "snapshot_id": snap.snapshot_id,
            "generated_at": snap.generated_at.isoformat(),
            "dqs_score": snap.quality.score,
            "fallback_used": snap.quality.fallback_used,
        },
        "mode": prov,
        "verdict": verdict,
        "narrative": narrative,
        "key_signals": key_signals,
        "token_usage": {"input": 0, "output": 0, "cached": True},
    }
