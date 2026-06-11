"""GET /api/v1/learning/{summary, calibration, mistakes}
POST /api/v1/learning/calibration/retrain
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from packages.learning import calibration_store, calibration_trainer, mistake_memory
from packages.learning.calibration import reliability_bins
from packages.learning.summary import build_summary
from packages.paper import state as paper_state

router = APIRouter(tags=["learning"])


@router.get("/learning/summary")
def get_learning_summary() -> dict:
    return build_summary()


@router.get("/learning/calibration")
def get_calibration() -> dict:
    params = calibration_store.load()
    # Mevcut state'ten reliability bins (uygulamak için fit'i tekrar koşmaya
    # gerek yok — sadece son örnekleri göster).
    s = paper_state.load()
    samples = [
        (float(t.predicted_confidence), bool(t.pnl_usd > 0))
        for t in s.recent_trades
        if getattr(t, "data_verified", False)
        and getattr(t, "predicted_confidence", None) is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]
    return {
        "params": asdict(params),
        "min_required": calibration_store.MIN_SAMPLES,
        "samples_in_state": len(samples),
        "bins": bins,
    }


@router.post("/learning/calibration/retrain")
def post_retrain_calibration() -> dict:
    return calibration_trainer.train()


@router.get("/learning/mistakes")
def get_mistakes() -> dict:
    mems = mistake_memory.summary()
    items = [asdict(m) for m in mems]
    # Verdict listesi (her fingerprint için)
    verdicts = []
    for m in mems:
        v = mistake_memory._verdict_for(m, m.fingerprint)
        verdicts.append(
            {
                "fingerprint": m.fingerprint,
                "action": v.action,
                "reason": v.reason,
                "size_factor": v.size_factor,
                "evidence": list(v.evidence),
            }
        )
    flagged = [v for v in verdicts if v["action"] in {"AVOID", "BOOST", "WARNING"}]
    return {
        "thresholds": mistake_memory.thresholds(),
        "records": items,
        "verdicts": verdicts,
        "flagged_count": len(flagged),
        "total_fingerprints": len(items),
    }
