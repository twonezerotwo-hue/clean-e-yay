"""Governor worker'ın son koşu özetini taşıyan küçük store (learning run_store
deseni). file-backed JSON, env path override, atomik yazım, bozuk → None.

Worker yazar, governor report okur. PAPER_SAFE — yalnızca metadata.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

_LOCK = threading.Lock()


def _path() -> Path:
    p = Path(os.environ.get("GOVERNOR_RUN_PATH", "data/runtime/governor_run.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def save(run: dict) -> dict:
    path = _path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return run


def load() -> dict | None:
    path = _path()
    with _LOCK:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return data if isinstance(data, dict) else None


__all__ = ["load", "save"]
