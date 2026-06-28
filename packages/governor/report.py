"""Governor read-only özet — "agent bugün ne öğrendi / ne buldu / ne öneriyor /
ne owner onayı bekliyor / hangi veriye güvenmiyor".

Yeni bir hesap YAPMAZ; yalnızca var olan store/özet fonksiyonlarını toplar.
Her kaynak best-effort sarmalanır: biri patlarsa rapor düşmez, o bölüm
`available: false` döner (crash-safe, dürüst — uydurma yok).

PAPER_SAFE / NO_EXECUTION: yalnızca okur. Live provider çağırmaz (alt
fonksiyonlar network-free store'lardan okur).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_log = logging.getLogger(__name__)


def _safe(fn: Callable[[], Any]) -> dict:
    """Bir özet kaynağını güvenle çağır; hata → {available: false, error}."""
    try:
        value = fn()
        return {"available": True, "data": value}
    except Exception as exc:  # best-effort — rapor asla patlamaz
        _log.warning("governor.report source failed: %s", exc)
        return {"available": False, "error": str(exc)[:200]}


def _learned() -> dict:
    from packages.learning.summary import build_summary

    s = build_summary()
    if not isinstance(s, dict):
        return {}
    # Üst düzey vurgular (varsa); tam özet zaten /learning/summary'de.
    keys = (
        "outcomes_total",
        "verified_outcomes",
        "sample_sufficient",
        "by_timeframe",
        "by_dominant_module",
        "proposal_status",
        "worker_last_run",
    )
    return {k: s[k] for k in keys if k in s}


def _missed() -> dict:
    from packages.learning import missed_opportunity

    return missed_opportunity.summary_viewmodel()


def _proposals() -> dict:
    from packages.governor import proposals

    return proposals.summary_viewmodel()


def _tasks() -> dict:
    from packages.governor import tasks

    return tasks.summary_viewmodel()


def _worker_last_run() -> dict | None:
    from packages.governor import run_store

    return run_store.load()


def _other_pending_approvals() -> dict:
    """Governor defteri DIŞINDA, sistemde halihazırda owner onayı bekleyen
    mevcut owner-gated mekanizmalar (tek bakışta görünürlük)."""
    out: dict = {}
    try:
        from packages.learning import rebalance_store

        out["weights"] = rebalance_store.get_pending() is not None
    except Exception:
        out["weights"] = None
    try:
        from packages.learning import tf_target_store

        out["tf_targets"] = bool(tf_target_store.load().get("pending"))
    except Exception:
        out["tf_targets"] = None
    try:
        from packages.mode import store as mode_store

        out["mode_overrides_active"] = bool(mode_store.load_overrides())
    except Exception:
        out["mode_overrides_active"] = None
    return out


def _data_trust() -> dict:
    """Hangi veriye güvenmiyoruz? system_health'in network-free özetinden
    provider + DQS durumu."""
    from packages.ops.system_health import build_system_health

    h = build_system_health()
    if not isinstance(h, dict):
        return {}
    return {
        "providers": h.get("provider_summary"),
        "dqs": h.get("dqs_status"),
        "warnings": h.get("warnings"),
    }


def build_report() -> dict:
    """Tek read-only governor özeti. Hiçbir bölüm raporu düşürmez."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "paper_safe": True,
        "no_execution": True,
        "learned": _safe(_learned),
        "found_missed_opportunities": _safe(_missed),
        "tasks": _safe(_tasks),
        "proposals": _safe(_proposals),
        "other_pending_approvals": _safe(_other_pending_approvals),
        "data_trust": _safe(_data_trust),
        "worker_last_run": _safe(_worker_last_run),
        "note": (
            "Read-only özet. Governor işlem açmaz, ayar değiştirmez; yalnızca "
            "var olan store'lardan derler. Öneriler owner onayı bekler."
        ),
    }


__all__ = ["build_report"]
