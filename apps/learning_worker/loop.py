"""Standalone learning loop daemon — runs learning_worker.run_once() forever.

    python -m apps.learning_worker.loop

This exists separately from apps/supervisor because supervisor bundles the
API + tick_worker + learning loop into one event loop, which blocks
cockpit/brief for ~23s per cycle (see scripts/start-dashboard.ps1 comment).
The deployed architecture runs API and tick_worker as their own plain
processes; this script is the matching standalone process for the learning
loop, started the same way (no API, no tick_worker — those already run
elsewhere).

Env:
    LEARNING_INTERVAL_SEC (default 300)
"""
from __future__ import annotations

import logging
import os
import signal
import time

from apps.learning_worker.main import run_once

_log = logging.getLogger("apps.learning_worker.loop")
_STOP = False


def _handle_stop(signum: int, frame: object) -> None:
    global _STOP
    _STOP = True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    interval = int(os.environ.get("LEARNING_INTERVAL_SEC", "300"))
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    _log.info("learning loop started, interval=%ds", interval)
    while not _STOP:
        try:
            run_once()
        except Exception:
            _log.exception("learning run_once failed")
        for _ in range(interval):
            if _STOP:
                break
            time.sleep(1)
    _log.info("learning loop stopped")


if __name__ == "__main__":
    main()
