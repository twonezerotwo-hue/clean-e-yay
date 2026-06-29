"""Görev Kuyruğu — agent'ın kendi kendine ürettiği OBSERVE-ONLY görevler.

Sistemin "kendi işini çıkarması"nın motoru. `generate()` mevcut store'lara bakıp
gerekiyorsa görev üretir (örn. provider degraded → DATA_QUALITY_REVIEW P0).
`execute()` görevi koşar ve YALNIZCA bir rapor üretir.

DEĞİŞMEZ GÜVENLİK SINIRLARI (yapısal — bayrakla gevşetilemez)
------------------------------------------------------------
1. `can_change_policy` HER görevde False'tur ve `enqueue()` gelen değeri
   GÖRMEZDEN gelip zorla False yapar. Hiçbir görev weights/thresholds/risk/mode/
   paper'a YAZAMAZ.
2. Görev tipleri whitelist'tir ve her tip yalnızca READ-ONLY bir handler'a
   eşlenir (`_HANDLERS`). Handler'lar yalnızca mevcut özet/store okuma
   fonksiyonlarını çağırır — `attempt_open`, config yazımı, RiskGate çağrısı YOK.
3. `auto_execute` yalnızca raporlama anlamına gelir (read-only handler). Trade
   path'e ya da config'e otomatik yazma kapısı YOKTUR.

Desen proposals/rebalance store ile aynı: file-backed JSON, env path override,
atomik yazım, bozuk → boş. PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from packages.data.registry.loader import REPO_ROOT

_log = logging.getLogger(__name__)

TaskStatus = Literal["PENDING", "DONE", "FAILED"]

# Görev tipi → varsayılan öncelik (rapor §9). Yalnızca bu tipler kabul edilir.
#   P0 = güvenlik/veri hatası · P1 = açık pozisyon riski · P2 = kaçan fırsat/zarar
#   P3 = strateji optimizasyonu · P4 = dashboard/rapor
TASK_TYPES: dict[str, str] = {
    "DATA_QUALITY_REVIEW": "P0",
    "RISK_REVIEW": "P1",
    "MISSED_OPPORTUNITY_REVIEW": "P2",
    "TRADE_REVIEW": "P3",
    "MODE_REVIEW": "P3",
    "SYSTEM_HEALTH_REVIEW": "P4",
}
PRIORITIES = ("P0", "P1", "P2", "P3", "P4")

_HISTORY_CAP = 100
_QUEUE_CAP = 200
_LOCK = threading.Lock()


def _store_path() -> Path:
    p = Path(os.environ.get("GOVERNOR_TASKS_PATH", "data/runtime/governor_tasks.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"queue": [], "history": []}


def load() -> dict:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    for k in ("queue", "history"):
        if not isinstance(data.get(k), list):
            data[k] = []
    return data


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _safe_dict(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    try:
        json.dumps(value)
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _dedup_key(t: dict) -> tuple:
    return (t.get("task_type"), json.dumps(t.get("params") or {}, sort_keys=True))


def enqueue(
    task_type: str,
    *,
    subject: str = "",
    params: dict | None = None,
    priority: str | None = None,
    auto_execute: bool = True,
    source: str = "governor",
) -> dict | None:
    """Yeni görev kuyruğa al. Geçersiz tip → None. Aynı (tip, params) PENDING
    zaten varsa onu döner (çift kayıt yok).

    `can_change_policy` GİRDİDEN OKUNMAZ — daima False (yapısal invariant)."""
    if task_type not in TASK_TYPES:
        return None
    prio = priority if priority in PRIORITIES else TASK_TYPES[task_type]
    clean_params = _safe_dict(params)
    candidate = {"task_type": task_type, "params": clean_params}
    data = load()
    key = _dedup_key(candidate)
    for existing in data["queue"]:
        if _dedup_key(existing) == key:
            return existing
    task = {
        "task_id": uuid.uuid4().hex[:12],
        "task_type": task_type,
        "priority": prio,
        "subject": str(subject or task_type).strip()[:200],
        "params": clean_params,
        "status": "PENDING",
        "auto_execute": bool(auto_execute),
        "can_change_policy": False,  # YAPISAL: asla True olamaz
        "source": str(source or "governor")[:50],
        "created_at": datetime.now(UTC).isoformat(),
        "result": None,
    }
    data["queue"] = [*data["queue"], task][-_QUEUE_CAP:]
    _save(data)
    return task


def list_queue() -> list[dict]:
    """Bekleyen görevler, öncelik sırasına göre (P0 önce)."""
    q = load().get("queue", [])
    return sorted(q, key=lambda t: PRIORITIES.index(t.get("priority", "P4")))


def get(task_id: str) -> dict | None:
    data = load()
    for bucket in ("queue", "history"):
        for t in data[bucket]:
            if t.get("task_id") == task_id:
                return t
    return None


# ── READ-ONLY handler'lar (config'e/paper'a ASLA yazmaz) ─────────────────────

def _h_data_quality(params: dict) -> dict:
    from packages.ops.system_health import build_system_health

    h = build_system_health()
    return {
        "providers": h.get("provider_summary"),
        "dqs": h.get("dqs_status"),
        "warnings": h.get("warnings"),
    }


def _h_risk(params: dict) -> dict:
    from packages.ops.system_health import build_system_health

    h = build_system_health()
    return {"risk_halt": h.get("risk_halt_status"), "warnings": h.get("warnings")}


def _h_missed(params: dict) -> dict:
    from packages.learning import missed_opportunity

    return missed_opportunity.summary_viewmodel()


def _h_trade(params: dict) -> dict:
    from packages.learning.summary import build_summary

    return build_summary()


def _h_mode(params: dict) -> dict:
    from packages.mode import config as mode_config

    cfg = mode_config.load_config()
    return {
        "disabled_trade_profiles": list(cfg.disabled_trade_profiles),
        "enabled_trade_profiles": list(cfg.enabled_trade_profiles),
        "focus_mode": cfg.focus_mode,
    }


def _h_system(params: dict) -> dict:
    from packages.ops.system_health import build_system_health

    return build_system_health()


_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "DATA_QUALITY_REVIEW": _h_data_quality,
    "RISK_REVIEW": _h_risk,
    "MISSED_OPPORTUNITY_REVIEW": _h_missed,
    "TRADE_REVIEW": _h_trade,
    "MODE_REVIEW": _h_mode,
    "SYSTEM_HEALTH_REVIEW": _h_system,
}


def execute(task_id: str) -> dict | None:
    """Görevi koş → READ-ONLY rapor üret, DONE işaretle, history'e taşı.

    Handler patlasa bile kuyruk bozulmaz (FAILED + error). Hiçbir handler
    config/paper yazmaz (yapısal)."""
    data = load()
    idx = next(
        (i for i, t in enumerate(data["queue"]) if t.get("task_id") == task_id), None
    )
    if idx is None:
        return None
    task = dict(data["queue"].pop(idx))
    handler = _HANDLERS.get(task["task_type"])
    try:
        if handler is None:  # whitelist garantisi nedeniyle pratikte olmaz
            raise KeyError(f"handler yok: {task['task_type']}")
        report = handler(task.get("params") or {})
        task.update(status="DONE", result=report)
    except Exception as exc:  # best-effort — kuyruk asla çökmez
        _log.warning("governor task %s failed: %s", task_id, exc)
        task.update(status="FAILED", result={"error": str(exc)[:200]})
    task["executed_at"] = datetime.now(UTC).isoformat()
    data["history"] = [task, *data["history"]][:_HISTORY_CAP]
    _save(data)
    return task


def generate() -> list[dict]:
    """Mevcut store'lara bakıp gereken OBSERVE-ONLY görevleri üret (dedup'lu).

    Best-effort: her sonda hatayı yutar (görev üretimi sistemi düşürmez)."""
    created: list[dict] = []

    def _add(task_type: str, subject: str, params: dict | None = None) -> None:
        clean_params = _safe_dict(params)
        key = _dedup_key({"task_type": task_type, "params": clean_params})
        already_pending = any(_dedup_key(t) == key for t in load().get("queue", []))
        t = enqueue(task_type, subject=subject, params=clean_params)
        if not already_pending and t and t.get("status") == "PENDING" and t not in created:
            created.append(t)

    try:
        from packages.ops.system_health import build_system_health

        h = build_system_health()
        prov = h.get("provider_summary") or {}
        provider_counts = prov.get("providers") if isinstance(prov.get("providers"), dict) else {}
        degraded_count = int(prov.get("degraded_count") or provider_counts.get("degraded") or 0)
        down_count = int(provider_counts.get("down") or 0)
        if degraded_count > 0 or down_count > 0:
            _add(
                "DATA_QUALITY_REVIEW",
                "Provider degraded/down — veri kalitesini incele",
                {"provider_summary": prov},
            )
        dqs = h.get("dqs_status") or {}
        dqs_status = dqs.get("status") if isinstance(dqs, dict) else dqs
        if str(dqs_status or "").upper() in {"BLOCKED", "DEGRADED"}:
            _add("DATA_QUALITY_REVIEW", "DQS düşük — neden?", {"dqs": dqs})
        halt = h.get("risk_halt_status") or {}
        if halt.get("active") or halt.get("halts"):
            _add("RISK_REVIEW", "Aktif halt — doğru muydu?", {"halt": halt})
    except Exception as exc:
        _log.warning("generate(system_health) failed: %s", exc)

    try:
        from packages.learning import missed_opportunity

        m = missed_opportunity.summary_viewmodel()
        total = m.get("total") or m.get("tracked") or m.get("count") or 0
        if isinstance(total, int) and total > 0:
            _add(
                "MISSED_OPPORTUNITY_REVIEW",
                "Kaçan fırsatları gözden geçir",
                {"total": total},
            )
    except Exception as exc:
        _log.warning("generate(missed) failed: %s", exc)

    try:
        from packages.learning.summary import build_summary

        s = build_summary()
        if s.get("sample_sufficient"):
            _add("TRADE_REVIEW", "Yeterli örnek — trade sonuçlarını incele", {})
    except Exception as exc:
        _log.warning("generate(learning) failed: %s", exc)

    return created


def clear() -> None:
    path = _store_path()
    with _LOCK:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def summary_viewmodel(limit: int = 30) -> dict:
    """Dashboard için read-only görünüm: kuyruk (öncelikli) + son geçmiş +
    öncelik sayaçları."""
    q = list_queue()
    by_prio: dict[str, int] = {}
    for t in q:
        p = t.get("priority", "P4")
        by_prio[p] = by_prio.get(p, 0) + 1
    return {
        "task_types": dict(TASK_TYPES),
        "queue": q,
        "queue_count": len(q),
        "queue_by_priority": by_prio,
        "history": load().get("history", [])[:limit],
        "note": (
            "Görevler yalnızca okur ve rapor üretir (can_change_policy=False); "
            "config/paper/RiskGate'e yazamazlar."
        ),
    }


__all__ = [
    "PRIORITIES",
    "TASK_TYPES",
    "clear",
    "enqueue",
    "execute",
    "generate",
    "get",
    "list_queue",
    "load",
    "summary_viewmodel",
]
