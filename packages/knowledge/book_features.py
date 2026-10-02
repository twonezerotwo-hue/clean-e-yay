"""Book-principle feature extraction in shadow mode.

These features translate the books' repeatable rules into observable fields from
the existing closed-bar technical result.  They are deliberately not consumed by
the score, confidence, sizing, RiskGate, or execution path until labelled replay
promotes them.
"""
from __future__ import annotations

from typing import Any


def _feature_cell(timeframe: str, result: Any) -> dict[str, Any]:
    summary = result.timeframe_summary
    pattern = result.chart_pattern_analysis
    reversal = result.reversal_signals
    fib = result.fibonacci_analysis
    zones = list(result.confluence_zones or [])
    confirmations = [signal.name for signal in result.confirmation_signals if signal.fired]
    active_patterns = [item.name for item in (pattern.active_patterns if pattern else [])]
    divergences = [item.type for item in (reversal.signals if reversal else [])]

    structure = active_patterns[0] if active_patterns else None
    side = (
        "long" if summary.bias == "BULLISH"
        else "short" if summary.bias == "BEARISH"
        else None
    )
    stop_ready = result.key_levels.stop_reference is not None
    target_ready = result.key_levels.target_reference is not None
    fibonacci_ready = bool(fib is not None and fib.validity == "sane")
    evidence_items = [
        result.data_quality.status == "OK",
        side is not None,
        bool(confirmations),
        bool(zones),
        fibonacci_ready,
        bool(structure and structure != "ranging"),
        bool(divergences),
        stop_ready,
        target_ready,
    ]

    methods: list[str] = []
    if structure in {"uptrend_structure", "downtrend_structure"}:
        methods.append("structure_breakout_retest")
    if zones:
        methods.append("support_resistance_zone")
    if stop_ready and target_ready:
        methods.append("risk_reward_and_structure_stop")
    if structure in {"uptrend_structure", "downtrend_structure"}:
        methods.append("trend_continuation_patterns")
    if divergences:
        methods.append("rsi_macd_divergence")
    if fibonacci_ready:
        methods.append("elliott_wave_plus_fibonacci")

    return {
        "timeframe": timeframe,
        "side": side,
        "structure": structure,
        "confirmation_count": len(confirmations),
        "confirmations": confirmations,
        "confluence_zone_count": len(zones),
        "divergences": divergences,
        "fibonacci_valid": fibonacci_ready,
        "invalidation_ready": stop_ready,
        "target_ready": target_ready,
        "evidence_score": min(100, sum(evidence_items) * 100 // len(evidence_items)),
        "methods": methods,
        "promotion_status": "shadow",
        "evidence_only": True,
    }


def build_from_agent(agent: Any) -> dict[str, Any]:
    """Build replay-ready book features from an existing technical agent output."""
    per_tf = getattr(agent, "per_timeframe", {}) or {}
    cells = []
    for key, result in per_tf.items():
        if result is None:
            continue
        cells.append(_feature_cell(getattr(result, "timeframe", key), result))
    order = {"1w": 0, "1d": 1, "4h": 2, "1h": 3, "15m": 4}
    cells.sort(key=lambda item: order.get(item["timeframe"], 99))
    directional = [cell for cell in cells if cell["side"]]
    sides = {cell["side"] for cell in directional}
    return {
        "mode": "evidence_only",
        "promotion_status": "shadow",
        "promoted_to_decision": False,
        "applied": False,
        "multi_timeframe_alignment": len(sides) == 1 and bool(directional),
        "cells": cells,
    }


__all__ = ["build_from_agent"]
