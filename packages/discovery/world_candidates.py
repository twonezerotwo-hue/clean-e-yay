"""World-state driven asset candidates; promotion remains owner-controlled."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from packages.data.registry import assets as asset_registry


def build_world_candidates(
    graph_context: Mapping[str, Any] | None,
    scenario_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Rank topology/scenario candidates without changing the live universe."""
    graph = graph_context or {}
    scores: dict[str, float] = {}
    reasons: dict[str, set[str]] = {}
    channels: dict[str, set[str]] = {}
    for symbol in graph.get("affected_assets") or ():
        key = str(symbol).upper()
        scores[key] = max(scores.get(key, 0.0), 0.25)
        reasons.setdefault(key, set()).add("world_graph_topology")
    for event in (scenario_report or {}).get("events") or ():
        for scenario in event.get("scenarios") or ():
            try:
                probability = max(0.0, min(1.0, float(scenario.get("probability") or 0.0)))
            except (TypeError, ValueError):
                # A malformed upstream scenario must never break world-state
                # construction; it is simply not promotable to a candidate.
                continue
            for symbol, direction in (scenario.get("affected_assets") or {}).items():
                key = str(symbol).upper()
                try:
                    magnitude = abs(float(direction or 0.0))
                except (TypeError, ValueError):
                    continue
                scores[key] = scores.get(key, 0.0) + probability * magnitude
                reasons.setdefault(key, set()).add(f"scenario:{scenario.get('scenario_id', 'unknown')}")
                channels.setdefault(key, set()).update(str(x) for x in scenario.get("factor_channels") or ())
    candidates: list[dict[str, Any]] = []
    for symbol, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        asset = asset_registry.get(symbol)
        trade_role = bool(asset and "trade" in asset.roles)
        candidates.append({
            "symbol": symbol,
            "world_score": round(min(1.0, score), 6),
            "reasons": sorted(reasons.get(symbol, set())),
            "factor_channels": sorted(channels.get(symbol, set())),
            "asset_class": asset.asset_class if asset else "unknown",
            "known_asset": asset is not None,
            "trade_universe_member": trade_role,
            "liquidity_status": "UNKNOWN",
            "promotion_status": "OBSERVE_ONLY",
            "missing_inputs": ["liquidity", "provider_identity"] if asset is None else ["liquidity"],
        })
    return {
        "status": "OK" if candidates else "NO_MATCH",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "promotion_policy": "owner_or_discovery_promotion_only",
        "warnings": ["candidate_list_does_not_change_trade_universe"] if candidates else [],
    }


__all__ = ["build_world_candidates"]
