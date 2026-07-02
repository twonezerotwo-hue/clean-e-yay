"""O1 — system health ViewModel (pure read; network-free).

Worker heartbeat + snapshot store + halt store + paper audit'ten 7/24
operasyonel sağlık özeti üretir. STALE tespiti heartbeat yaşına göre (eşikler
config/env'den, güvenli default). Üretilen "warnings" owner uyarısıdır —
execution alert DEĞİL: trade açmaz, RiskGate/DQS/KillSwitch/halt bypass etmez.

PAPER_SAFE / NO_EXECUTION. Frontend hesap yapmaz — bu ViewModel'i gösterir.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from packages.data import snapshot_store
from packages.ops import heartbeat
from packages.paper import audit as paper_audit
from packages.risk import halt as halt_store

TICK_WORKER = "tick_worker"
LEARNING_WORKER = "learning_worker"

DEFAULT_TICK_STALE_SEC = 120       # ~4× 30sn tick interval
DEFAULT_LEARNING_STALE_SEC = 3600  # 1 saat

_METRIC_DEFAULTS = (
    ("cycle_count", 0),
    ("snapshots_written", 0),
    ("decisions_generated", 0),
    ("paper_actions", 0),
    ("learning_outcomes_seen", 0),
    ("proposals_generated", 0),
)


def _stale_threshold(env: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(env, default)))
    except (ValueError, TypeError):
        return default


def _age_seconds(ts: str | None, now: datetime) -> float | None:
    if not ts:
        return None
    try:
        return round((now - datetime.fromisoformat(ts)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _unknown_worker(name: str) -> dict:
    view = {
        "worker_name": name,
        "status": "UNKNOWN",
        "stale": True,
        "run_id": None,
        "started_at": None,
        "completed_at": None,
        "last_success_at": None,
        "last_error": None,
        "age_seconds": None,
        "duration_ms": None,
        # F2-1 — MTM salt-gözlem alanları (tick_worker yazar; gate girdisi değil).
        "unrealized_pnl_usd": None,
        "mtm_equity_usd": None,
    }
    for k, dv in _METRIC_DEFAULTS:
        view[k] = dv
    return view


def _worker_view(name: str, threshold_sec: int, now: datetime) -> dict:
    hb = heartbeat.load(name)
    if hb is None:
        return _unknown_worker(name)  # hiç çalışmadı
    last_contact = hb.get("completed_at") or hb.get("started_at")
    age = _age_seconds(last_contact, now)
    stored = str(hb.get("status", "UNKNOWN"))
    stale = age is None or age > threshold_sec
    if stored == "FAILED":
        status = "FAILED"          # hata stale olsa bile görünür kalsın
    elif stale:
        status = "STALE"           # uzun süredir cycle yok / takıldı
    else:
        status = stored
    view = dict(hb)
    view["worker_name"] = name
    view["status"] = status
    view["stale"] = stale
    view["age_seconds"] = age
    for k, dv in _METRIC_DEFAULTS:
        view.setdefault(k, dv)
    view.setdefault("duration_ms", None)
    view.setdefault("last_error", None)
    view.setdefault("last_success_at", None)
    # F2-1 — legacy heartbeat dosyaları MTM alanlarını taşımaz → None'a düşer.
    view.setdefault("unrealized_pnl_usd", None)
    view.setdefault("mtm_equity_usd", None)
    return view


def _provider_summary(provider_status: dict) -> dict:
    # "disabled" = config eksik (opsiyonel entegrasyon kapalı) — degraded değil.
    counts = {"ok": 0, "degraded": 0, "down": 0, "unknown": 0, "disabled": 0}
    for info in (provider_status or {}).values():
        raw = info.get("status") if isinstance(info, dict) else info
        st = str(raw or "unknown").lower()
        counts[st] = counts.get(st, 0) + 1
    return {
        "providers": counts,
        "degraded_count": counts.get("degraded", 0) + counts.get("down", 0),
        "total": sum(counts.values()),
    }


def build_system_health() -> dict:
    now = datetime.now(UTC)
    tick = _worker_view(
        TICK_WORKER, _stale_threshold("TICK_STALE_SEC", DEFAULT_TICK_STALE_SEC), now
    )
    learning = _worker_view(
        LEARNING_WORKER,
        _stale_threshold("LEARNING_STALE_SEC", DEFAULT_LEARNING_STALE_SEC),
        now,
    )

    latest = snapshot_store.latest()
    store_status = snapshot_store.status()
    snap_count = int(store_status.get("snapshot_count", 0) or 0)
    dqs_status = ((latest or {}).get("dqs") or {}).get("status")
    provider_summary = _provider_summary((latest or {}).get("provider_status") or {})

    active = halt_store.active_halts()
    risk_halt_status = {
        "active": bool(active),
        "count": len(active),
        "types": [h.type for h in active],
    }

    audit_errors = int((paper_audit.summary().get("counts") or {}).get("ERROR", 0))

    # last_successful_tick: heartbeat last_success_at (fallback: snapshot generated_at).
    last_successful_tick = tick.get("last_success_at") or (latest or {}).get("generated_at")
    last_learning_run = learning.get("last_success_at") or learning.get("completed_at")

    stale_workers = [w["worker_name"] for w in (tick, learning) if w["stale"]]

    # Owner warning'leri (sadece RAPOR — trade açmaz, RiskGate bypass etmez).
    warnings: list[str] = []
    if stale_workers:
        warnings.append("worker_stale")
    if tick["stale"]:
        warnings.append("stale_dashboard_state")
    if provider_summary["degraded_count"] > 0:
        warnings.append("provider_degraded")
    if dqs_status == "BLOCKED":
        warnings.append("dqs_blocked")
    if snap_count == 0:
        warnings.append("snapshot_store_empty")
    if learning["status"] == "NO_DATA":
        warnings.append("learning_worker_no_data")
    if audit_errors > 0:
        warnings.append("paper_audit_errors")
    if risk_halt_status["active"]:
        warnings.append("active_halt")

    # Cold-start / kullanıcı-eylemi gerektiren beklenen durumlar overall'u
    # degraded'a düşürmesin (warning yine raporlanır).
    INFO_ONLY = {"learning_worker_no_data", "snapshot_store_empty"}
    severe = [w for w in warnings if w not in INFO_ONLY]

    return {
        "api_status": "degraded" if severe else "ok",
        "paper_safe": True,
        "no_execution": True,
        "workers": {"tick_worker": tick, "learning_worker": learning},
        "stale_workers": stale_workers,
        "last_successful_tick": last_successful_tick,
        "last_learning_run": last_learning_run,
        "provider_summary": provider_summary,
        "dqs_status": dqs_status,
        "snapshot_store_status": store_status,
        "risk_halt_status": risk_halt_status,
        "warnings": warnings,
    }


__all__ = ["build_system_health"]
