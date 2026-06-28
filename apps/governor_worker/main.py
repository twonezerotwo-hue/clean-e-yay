"""Governor worker — self-managing döngünün motoru (OBSERVE-ONLY).

Üç-süreç deseninde DÖRDÜNCÜ süreç. learning_worker gibi **tek-seferlik**:
`run_once()` + dış zamanlayıcı (cron/launchd timer) — `restart-always` DEĞİL
(spin-loop yapar). api/tick/learning'den bağımsızdır; çökerse onları etkilemez.

Her koşuda:
  1. generate()  — mevcut store sinyallerinden observe-only görev üretir (dedup).
  2. execute()   — auto_execute görevleri koşar → YALNIZCA read-only rapor.
  3. run_store + heartbeat'e koşu özetini yazar.

DEĞİŞMEZ GÜVENLİK SINIRLARI
---------------------------
- `attempt_open()` ASLA çağrılmaz (paper açılışı yalnızca tick_worker'da — bkz.
  ARCHITECTURE §7.5). Bu worker import bile etmez.
- Görevler ve handler'ları config/paper/RiskGate'e yazamaz (packages/governor/
  tasks.py yapısal invariant'ları).
- Worker ASLA patlamaz (her aşama defensive). Hata → COMPLETED_WITH_ERRORS.

Çalıştırma:
    python -m apps.governor_worker.main
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import UTC, datetime

from packages.governor import run_store, tasks
from packages.ops import heartbeat

log = logging.getLogger("governor_worker")

WORKER_NAME = "governor_worker"

# Bir koşuda kaç auto_execute görevi koşulacağı (runaway koruması).
MAX_EXECUTE_PER_RUN = int(os.environ.get("GOVERNOR_MAX_EXECUTE_PER_RUN", "20"))

_HB_STATUS = {
    "COMPLETED": "OK",
    "COMPLETED_WITH_ERRORS": "DEGRADED",
    "NO_DATA": "NO_DATA",
}


def run_once() -> dict:
    """Tek governor koşusu; run metadata döner + run_store + heartbeat'e yazar."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    errors: list[str] = []
    generated = 0
    executed = 0
    executed_ids: list[str] = []

    # 1) Görev üret (observe-only, dedup'lu).
    try:
        created = tasks.generate()
        generated = len(created)
    except Exception as exc:  # defensive — worker patlamaz
        errors.append(f"generate:{type(exc).__name__}")

    # 2) auto_execute bekleyen görevleri koş (öncelik sırası, read-only).
    try:
        pending = [t for t in tasks.list_queue() if t.get("auto_execute")]
        for t in pending[:MAX_EXECUTE_PER_RUN]:
            rec = tasks.execute(t["task_id"])
            if rec is not None:
                executed += 1
                executed_ids.append(rec["task_id"])
    except Exception as exc:  # defensive
        errors.append(f"execute:{type(exc).__name__}")

    if errors:
        status = "COMPLETED_WITH_ERRORS"
    elif generated == 0 and executed == 0:
        status = "NO_DATA"
    else:
        status = "COMPLETED"

    run = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "tasks_generated": generated,
        "tasks_executed": executed,
        "executed_ids": executed_ids,
        "errors": errors,
    }
    try:
        run_store.save(run)
    except Exception as exc:  # defensive
        log.warning("governor run_store save failed: %s", exc)

    heartbeat.record(
        WORKER_NAME,
        status=_HB_STATUS.get(status, "OK"),
        run_id=run_id,
        started_at=started_at,
        completed_at=run["completed_at"],
        last_error="; ".join(errors) if errors else None,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    log.info(
        "governor run: status=%s generated=%s executed=%s",
        status,
        generated,
        executed,
    )
    return run


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_once()
