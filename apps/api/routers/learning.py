"""GET /api/v1/learning/{summary, calibration, mistakes}
POST /api/v1/learning/calibration/retrain
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from packages.learning import (
    calibration_store,
    calibration_trainer,
    historical_edge,
    mistake_memory,
    tf_weight_trainer,
)
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


@router.get("/learning/tf-weights")
def get_tf_weights() -> dict:
    """Step 8 — per-TF calibration + the trust-gated tf_weights proposal (read-only).

    Owner-facing view: which timeframes are validated (CALIBRATED) and what weight
    changes the verified outcomes suggest. Informational — live weights are never
    moved here (owner approval, never auto-apply)."""
    return tf_weight_trainer.report_viewmodel()


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


@router.get("/learning/historical-edge")
def get_historical_edge(fingerprint: str) -> dict:
    """Fuzzy-similarity historical edge — verilen fingerprint'e benzer geçmiş
    trade'lerin winrate/avg_pnl özeti. Read-only; karar zincirini etkilemez
    (mistake_memory exact-match gate'inin tamamlayıcısı, ondan ayrı)."""
    result = historical_edge.compute_edge(fingerprint)
    return {
        "similarity_weights": historical_edge.active_similarity_weights(),
        "result": historical_edge.edge_to_dict(result),
    }
