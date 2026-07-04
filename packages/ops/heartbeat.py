"""O1 — worker heartbeat store (file-backed, atomik).

tick_worker / learning_worker her cycle'da heartbeat yazar; `system/health`
bunları okuyup STALE/FAILED tespit eder. Tek dosya
`data/runtime/worker_heartbeats.json` = {worker_name: WorkerHeartbeat}.

Kurallar: atomik write (temp + os.replace), bozuk/eksik dosya → default (crash
yok), yazım/okuma hatası ASLA çağıranı patlatmaz. Test override:
`WORKER_HEARTBEAT_PATH` (env her çağrıda okunur → reload gerekmez).

PAPER_SAFE / NO_EXECUTION: yalnızca kayıt tutar.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

DEFAULT_PATH = "data/runtime/worker_heartbeats.json"

# Stored heartbeat statüleri. STALE/UNKNOWN system_health'te TÜRETİLİR (burada yazılmaz).
STATUSES = ("RUNNING", "OK", "DEGRADED", "FAILED", "NO_DATA")
_ALIVE = {"OK", "DEGRADED", "NO_DATA"}      # last_success_at güncellenir
_TERMINAL = {"OK", "DEGRADED", "FAILED", "NO_DATA"}  # cycle_count artar

_LOCK = threading.Lock()


def _path() -> Path:
    p = Path(os.environ.get("WORKER_HEARTBEAT_PATH", DEFAULT_PATH))
    return p if p.is_absolute() else REPO_ROOT / p


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_all() -> dict[str, dict]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}  # bozuk dosya → default (crash yok)


def load(worker_name: str) -> dict | None:
    hb = load_all().get(worker_name)
    return hb if isinstance(hb, dict) else None


def _save(all_hb: dict[str, dict]) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(all_hb, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass  # heartbeat ASLA worker'ı kesmez


def record(
    worker_name: str,
    *,
    status: str,
    run_id: str,
    started_at: str,
    completed_at: str | None = None,
    last_error: str | None = None,
    snapshots_written: int = 0,
    decisions_generated: int = 0,
    paper_actions: int = 0,
    learning_outcomes_seen: int = 0,
    proposals_generated: int = 0,
    duration_ms: int | None = None,
    unrealized_pnl_usd: float | None = None,
    mtm_equity_usd: float | None = None,
    degraded_reasons: list[str] | None = None,
) -> dict:
    """Heartbeat yaz (atomik); yazılan dict'i döner (best-effort).

    `cycle_count` yalnızca terminal statüde (OK/DEGRADED/FAILED/NO_DATA) artar;
    `last_success_at` OK/DEGRADED/NO_DATA'da güncellenir, FAILED/RUNNING'de prior
    korunur (böylece "en son ne zaman başarılı oldu" bilgisi kaybolmaz).
    """
    with _LOCK:
        all_hb = load_all()
        prior = all_hb.get(worker_name) or {}
        terminal = status in _TERMINAL
        cycle_count = int(prior.get("cycle_count", 0) or 0) + (1 if terminal else 0)
        if status in _ALIVE:
            last_success_at = completed_at or _utc_iso()
        else:
            last_success_at = prior.get("last_success_at")
        hb = {
            "worker_name": worker_name,
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "last_success_at": last_success_at,
            "last_error": last_error,
            "cycle_count": cycle_count,
            "snapshots_written": int(snapshots_written),
            "decisions_generated": int(decisions_generated),
            "paper_actions": int(paper_actions),
            "learning_outcomes_seen": int(learning_outcomes_seen),
            "proposals_generated": int(proposals_generated),
            "duration_ms": duration_ms,
            # F2-1 — MTM salt-gözlem: tick_worker cycle sonunda yazar; RiskGate
            # girdisi DEĞİL. None = bu cycle'da ölçüm yok (ör. FAILED).
            "unrealized_pnl_usd": (
                None if unrealized_pnl_usd is None else float(unrealized_pnl_usd)
            ),
            "mtm_equity_usd": (
                None if mtm_equity_usd is None else float(mtm_equity_usd)
            ),
            # S1-4 — DEGRADED'in NEDENİ görünür olsun (additive): hangi girdi
            # bozuk? Boş liste = sebep yok (status zaten OK) veya eski kayıt.
            "degraded_reasons": list(degraded_reasons or []),
        }
        all_hb[worker_name] = hb
        _save(all_hb)
        return hb


__all__ = ["STATUSES", "load", "load_all", "record"]
