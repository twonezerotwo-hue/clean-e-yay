"""Ninety-day paper forward-test ledger (observe-only).

The clock starts once, then remains immutable. Each learning run recomputes
metrics from canonical paper outcomes; it never opens, closes, or promotes a
position and never sends a broker order.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.learning.outcomes import outcomes_from_state
from packages.ops.store import write_text_atomic

DEFAULT_PATH = "data/runtime/forward_test_90d.json"
DURATION = timedelta(days=90)
MIN_CLOSED = 100


def _path() -> Path:
    return Path(os.environ.get("FORWARD_TEST_90D_PATH", DEFAULT_PATH))


def _parse(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _auto(o: object) -> bool:
    reason = str(getattr(o, "open_reason", "") or "").lower()
    if reason.startswith(("owner", "manual")) or bool(getattr(o, "exploration", False)):
        return False
    return True


def _metrics(outcomes: list[object]) -> dict[str, Any]:
    closed = [o for o in outcomes if getattr(o, "closed_at", None)]
    wins = [o for o in closed if float(getattr(o, "pnl", 0.0) or 0.0) > 0]
    pnl = [float(getattr(o, "pnl", 0.0) or 0.0) for o in closed]
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    r_values = [float(o.r_multiple) for o in closed if getattr(o, "r_multiple", None) is not None]
    return {
        "closed": len(closed),
        "open_or_unresolved": len(outcomes) - len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "win_rate": round(len(wins) / len(closed), 6) if closed else None,
        "net_pnl": round(sum(pnl), 6),
        "avg_pnl": round(sum(pnl) / len(pnl), 6) if pnl else None,
        "expectancy_r": round(sum(r_values) / len(r_values), 6) if r_values else None,
        "max_drawdown": round(max_dd, 6),
        "verified": sum(1 for o in closed if bool(getattr(o, "data_verified", False))),
    }


def run(*, now: datetime | None = None, outcomes: list[object] | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    p = _path()
    existing: dict[str, Any] = {}
    try:
        existing = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        existing = {}
    started = _parse(existing.get("started_at")) or now
    target = started + DURATION
    end = min(now, target)
    all_outcomes = outcomes if outcomes is not None else outcomes_from_state()
    scoped = []
    excluded_incomplete = 0
    for o in all_outcomes:
        if not _auto(o):
            continue
        opened = _parse(getattr(o, "opened_at", None))
        if opened is None or opened < started or opened > end:
            continue
        if getattr(o, "data_verified", None) is False or getattr(o, "provenance_complete", None) is False:
            excluded_incomplete += 1
            continue
        scoped.append(o)
    metrics = _metrics(scoped)
    complete = now >= target
    promotion_ready = bool(
        complete
        and metrics["closed"] >= MIN_CLOSED
        and (metrics["net_pnl"] or 0) > 0
        and (metrics["expectancy_r"] or 0) > 0
        and metrics["verified"] >= max(1, int(metrics["closed"] * 0.9))
    )
    status = "COMPLETE" if complete else "RUNNING"
    report = {
        "generated_at": now.isoformat(),
        "engine": "paper_forward_test_90d_v1",
        "status": status,
        "started_at": started.isoformat(),
        "target_end": target.isoformat(),
        "elapsed_days": max(0.0, min(90.0, (now - started).total_seconds() / 86_400)),
        "remaining_days": max(0.0, (target - now).total_seconds() / 86_400),
        "scope": "clean automatic paper outcomes only; owner/manual, exploration and incomplete provenance excluded",
        "excluded_incomplete": excluded_incomplete,
        "metrics": metrics,
        "minimum_closed_required": MIN_CLOSED,
        "promotion_ready": promotion_ready,
        "paper_safe": True,
        "no_execution": True,
        "automatic_activation": False,
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(p, json.dumps(report, ensure_ascii=False, indent=2, default=str))
    except OSError:
        pass
    return report


def viewmodel() -> dict[str, Any]:
    return run()


__all__ = ["run", "viewmodel"]
