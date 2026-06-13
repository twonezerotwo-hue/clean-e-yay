"""Learning worker — periyodik kalibrasyon + walk-forward + auto-weight proposal.

L1 — her koşu run metadata üretir (run_id / status / skipped_reason /
outcomes_seen / proposals_generated / calibration_status / errors). Boş veri →
NO_DATA; beklenmedik hata → COMPLETED_WITH_ERRORS (worker ASLA patlamaz).
active weights owner approval olmadan DEĞİŞMEZ.

Çalıştırma:
    python -m apps.learning_worker.main
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from packages.learning import auto_weight_trainer as trainer
from packages.learning import (
    calibration_trainer,
    rebalance_store,
    run_store,
)
from packages.learning import (
    outcomes as outcomes_mod,
)
from packages.learning.summary import build_summary

log = logging.getLogger("learning_worker")

OUT_PATH = Path(os.environ.get("LEARNING_OUT_PATH", "data/runtime/learning_summary.json"))


def run_once() -> dict:
    """Tek learning koşusu; run metadata döner + run_store'a yazar."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(UTC).isoformat()
    errors: list[str] = []
    proposals_generated = 0
    calibration_status = "UNKNOWN"
    skipped_reason: str | None = None

    try:
        outcomes_seen = len(outcomes_mod.outcomes_from_state())
    except Exception as exc:  # defensive — worker patlamamalı
        outcomes_seen = 0
        errors.append(f"outcomes:{type(exc).__name__}")

    # Özet (boş state'te de güvenli — total=0).
    try:
        summary = build_summary()
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        log.info(
            "learning_summary written: total=%s win_rate=%s sharpe=%s",
            summary.get("total_trades"),
            summary.get("win_rate"),
            summary.get("sharpe"),
        )
    except Exception as exc:  # defensive
        errors.append(f"summary:{type(exc).__name__}")

    # G6: confidence calibration. Yetersiz veri → identity (a=1, b=0).
    try:
        cal = calibration_trainer.train()
        calibration_status = str(cal.get("status", "UNKNOWN"))
        log.info("calibration: %s n=%s", calibration_status, cal.get("samples"))
    except Exception as exc:  # defensive
        errors.append(f"calibration:{type(exc).__name__}")

    # G2: auto-weight trainer. Yeterli veri varsa pending proposal güncellenir;
    # active weights DEĞİŞMEZ — owner approval gerekir.
    try:
        result = trainer.train(regime="NEUTRAL")
        if isinstance(result, trainer.RebalanceProposal):
            rebalance_store.set_pending(trainer.proposal_to_dict(result))
            proposals_generated = 1
            log.info(
                "rebalance proposal pending: %s → %s (n=%s)",
                result.from_version,
                result.to_version,
                result.dataset_size,
            )
        else:
            skipped_reason = result.get("reason")
            log.info("rebalance trainer skipped: %s", result)
    except Exception as exc:  # defensive
        errors.append(f"trainer:{type(exc).__name__}")

    if errors:
        status = "COMPLETED_WITH_ERRORS"
    elif outcomes_seen == 0:
        status = "NO_DATA"
        skipped_reason = "no_closed_outcomes"  # net NO_DATA nedeni
    else:
        status = "COMPLETED"  # skipped_reason trainer'dan (örn. below_min_total)

    run = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "skipped_reason": skipped_reason,
        "outcomes_seen": outcomes_seen,
        "proposals_generated": proposals_generated,
        "calibration_status": calibration_status,
        "errors": errors,
    }
    run_store.save(run)
    return run


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_once()
