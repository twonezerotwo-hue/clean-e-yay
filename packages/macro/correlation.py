"""Small, deterministic event-to-price correlation summaries.

Only supplied observations are used.  There is no network, imputation or
promotion logic here; callers can persist the result as a shadow diagnostic.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any


def rolling_regime_correlation(rows: Iterable[dict[str, Any]], *, window: int = 90) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        try:
            asset = str(row.get("asset") or "").upper()
            regime = str(row.get("regime") or row.get("correlation_regime") or "UNKNOWN")
            timeframe = str(row.get("timeframe") or "1d")
            direction = str(row.get("direction") or "")
            forward = float(row["outcome_return"])
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if not asset or not math.isfinite(forward) or direction not in {"bullish", "bearish"}:
            continue
        bucket = grouped[(asset, regime, timeframe)]
        bucket.append({"direction": direction, "outcome": forward})
    output: list[dict[str, Any]] = []
    for (asset, regime, timeframe), values in sorted(grouped.items()):
        sample = values[-max(1, int(window)):]
        if not sample:
            continue
        signed = [item["outcome"] if item["direction"] == "bullish" else -item["outcome"] for item in sample]
        n = len(signed)
        mean = sum(signed) / n
        variance = sum((value - mean) ** 2 for value in signed)
        rho = None if n < 2 or variance <= 0 else round(sum((value - mean) * (idx - (n - 1) / 2) for idx, value in enumerate(signed)) / math.sqrt(variance * sum((idx - (n - 1) / 2) ** 2 for idx in range(n))), 6)
        output.append({
            "asset": asset,
            "regime": regime,
            "timeframe": timeframe,
            "n": n,
            "mean_signed_return": round(mean, 8),
            "hit_rate": round(sum(value > 0 for value in signed) / n, 6),
            "correlation": rho,
            "window": max(1, int(window)),
            "shadow_only": True,
        })
    return output


__all__ = ["rolling_regime_correlation"]
