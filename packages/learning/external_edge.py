"""External holdout edge report (observe-only).

The report evaluates the isolated historical challenger stream on a strictly
chronological holdout.  It never changes weights, paper state, gates, or order
behaviour; it only writes a measured artifact for review.
"""
from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.data.registry.loader import load_thresholds
from packages.learning import backtest_recon
from packages.ops.store import write_text_atomic

DEFAULT_PATH = "data/runtime/external_edge.json"
MIN_HOLDOUT = 100


def _path() -> Path:
    return Path(os.environ.get("EXTERNAL_EDGE_PATH", DEFAULT_PATH))


def _cost_fraction() -> float:
    """Round-trip cost from the same configured economics used by paper."""
    try:
        costs = (load_thresholds().get("trade_economics") or {}).get("costs") or {}
        return sum(float(costs.get(k, 0.0) or 0.0) for k in ("taker_fee_bps", "est_spread_bps", "est_slippage_bps")) / 10_000.0
    except Exception:
        # Conservative fallback matching thresholds_v1.0.yaml (15 bps).
        return 0.0015


def _records() -> list[dict[str, Any]]:
    rows = []
    for row in backtest_recon.read_challenger():
        try:
            as_of = datetime.fromisoformat(str(row.get("as_of", "")).replace("Z", "+00:00"))
            ret = float(row.get("directional_return"))
        except (TypeError, ValueError):
            continue
        if row.get("direction") not in {"bullish", "bearish"}:
            continue
        if not math.isfinite(ret):
            continue
        rows.append({**row, "_as_of": as_of, "_return": ret})
    return sorted(rows, key=lambda r: r["_as_of"])


def _wilson_lower(wins: int, n: int, z: float = 1.96) -> float | None:
    if n <= 0:
        return None
    p = wins / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return round((centre - spread) / den, 6)


def _metrics(rows: list[dict[str, Any]], cost: float) -> dict[str, Any]:
    net = [float(r["_return"]) - cost for r in rows]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in net:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "n": len(net),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(net), 6) if net else None,
        "win_rate_wilson_lower_95": _wilson_lower(len(wins), len(net)),
        "avg_net_return": round(sum(net) / len(net), 8) if net else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "cumulative_net_return": round(sum(net), 8),
        "max_drawdown_return": round(max_dd, 8),
        "symbols": sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}),
        "regimes": sorted({str(r.get("regime_label")) for r in rows if r.get("regime_label")}),
    }


def run(*, now: datetime | None = None, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    rows = _records() if records is None else sorted(records, key=lambda r: r["_as_of"])
    cost = _cost_fraction()
    split = int(len(rows) * 0.70)
    train_rows, holdout_rows = rows[:split], rows[split:]
    train = _metrics(train_rows, cost)
    holdout = _metrics(holdout_rows, cost)
    enough = holdout["n"] >= MIN_HOLDOUT
    positive = bool(
        enough
        and (holdout["avg_net_return"] or 0) > 0
        and (holdout["win_rate_wilson_lower_95"] or 0) > 0.5
        and (train["avg_net_return"] or 0) > 0
    )
    status = "READY" if positive else "UNPROVEN" if enough else "INSUFFICIENT"
    start = rows[0]["_as_of"].isoformat() if rows else None
    end = rows[-1]["_as_of"].isoformat() if rows else None
    report = {
        "generated_at": now.isoformat(),
        "engine": "external_edge_v1",
        "source": "backtest_challenger",
        "status": status,
        "paper_safe": True,
        "no_execution": True,
        "automatic_activation": False,
        "chronology": {"from": start, "to": end, "split_ratio": 0.70},
        "cost_model": {"round_trip_fraction": cost, "round_trip_bps": round(cost * 10_000, 4)},
        "train": train,
        "holdout": holdout,
        "decision": "external holdout is evidence only; no automatic promotion",
    }
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(p, json.dumps(report, ensure_ascii=False, indent=2, default=str))
    except OSError:
        pass
    return report


def run_if_due(*, max_age_seconds: float = 86_400, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    p = _path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(str(raw.get("generated_at", "")).replace("Z", "+00:00"))
        if (now - generated).total_seconds() <= max_age_seconds:
            return raw
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return run(now=now)


def viewmodel() -> dict[str, Any]:
    return run_if_due()


__all__ = ["run", "run_if_due", "viewmodel"]
