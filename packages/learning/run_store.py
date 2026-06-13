"""L1 — learning worker run metadata store (file-backed JSON, atomik).

Worker her koşusunda son run metadata'sını yazar: run_id / started_at /
completed_at / status / skipped_reason / outcomes_seen / proposals_generated /
calibration_status / errors. Summary endpoint bunu `worker_last_run` olarak
yüzeye çıkarır. Boş veri / hata → status SKIPPED/NO_DATA (crash yok).

PAPER_SAFE / NO_EXECUTION: yalnızca kayıt tutar.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

DEFAULT_PATH = "data/runtime/learning_run.json"


def _path() -> Path:
    p = Path(os.environ.get("LEARNING_RUN_PATH", DEFAULT_PATH))
    return p if p.is_absolute() else REPO_ROOT / p


def save(run: dict) -> dict:
    """Atomik yaz (temp + os.replace); yazım hatası yutulur (worker patlamaz)."""
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(run, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass
    return run


def load() -> dict | None:
    """Son run metadata'sı; yoksa/bozuksa None."""
    p = _path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None
