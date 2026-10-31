"""Gözlemlenebilirlik metrikleri (hedef mimari: op_obs) — salt okuma.

Tick'in aşama süreleri heartbeat kaydından okunur (son 60 tur): aşama başına son,
p50, p95 ve en yüksek. API ile tick ayrı süreçte olsa da aynı dosyadan okunur.
"""
from __future__ import annotations

from typing import Any

from packages.ops import heartbeat

_TICK_WORKER = "tick_worker"


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def tick_metrics() -> dict[str, Any]:
    hb = heartbeat.load(_TICK_WORKER) or {}
    history = [h for h in (hb.get("stage_history") or []) if isinstance(h, dict)]
    stages: dict[str, dict[str, float]] = {}
    for name in sorted({k for h in history for k in h}):
        vals = [float(h[name]) for h in history if name in h]
        stages[name] = {"last": round(vals[-1], 3), "p50": round(_pct(vals, 0.5), 3),
                        "p95": round(_pct(vals, 0.95), 3), "max": round(max(vals), 3)}
    return {
        "worker": _TICK_WORKER,
        "status": hb.get("status"),
        "cycle_count": hb.get("cycle_count"),
        "last_completed_at": hb.get("completed_at"),
        "decisions_last": hb.get("decisions_generated"),
        "samples": len(history),
        "stages_sec": stages,
    }


__all__ = ["tick_metrics"]
