"""Learning worker — periyodik kalibrasyon + walk-forward.

Çalıştırma:
    python -m apps.learning_worker.main
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

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
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_once()
