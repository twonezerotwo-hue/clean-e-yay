"""Learning worker — periyodik kalibrasyon + walk-forward + auto-weight proposal.

Çalıştırma:
    python -m apps.learning_worker.main
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from packages.learning import auto_weight_trainer as trainer
from packages.learning import calibration_trainer, rebalance_store
from packages.learning.summary import build_summary

log = logging.getLogger("learning_worker")

OUT_PATH = Path(os.environ.get("LEARNING_OUT_PATH", "data/runtime/learning_summary.json"))


def run_once() -> dict:
    summary = build_summary()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info(
        "learning_summary written: total=%s win_rate=%s sharpe=%s",
        summary["total_trades"],
        summary["win_rate"],
        summary.get("sharpe"),
    )

    # G6: confidence calibration. Yetersiz veri → identity (a=1, b=0).
    cal = calibration_trainer.train()
    log.info("calibration: %s n=%s", cal["status"], cal["samples"])

    # G2: auto-weight trainer. Yeterli veri varsa pending proposal güncellenir;
    # active weights değişmez — owner approval gerekir.
    result = trainer.train(regime="NEUTRAL")
    if isinstance(result, trainer.RebalanceProposal):
        rebalance_store.set_pending(trainer.proposal_to_dict(result))
        log.info(
            "rebalance proposal pending: %s → %s (n=%s)",
            result.from_version,
            result.to_version,
            result.dataset_size,
        )
    else:
        log.info("rebalance trainer skipped: %s", result)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_once()
