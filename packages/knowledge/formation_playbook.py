"""Book-grounded formation playbook for read-only decision explanations.

The playbook turns already-computed technical evidence into an auditable plan:
setup type, confirmation, invalidation, target and management policy.  It never
creates an action, changes size, or bypasses the existing economics/RiskGate.
"""
from __future__ import annotations

from typing import Any

METHOD_SCORES: tuple[dict[str, Any], ...] = (
    {"method": "structure_breakout_retest", "score": 9.0, "role": "primary", "reason": "Objective HH/HL or LH/LL structure, explicit invalidation and retest."},
    {"method": "support_resistance_zone", "score": 9.0, "role": "primary", "reason": "Level/zone gives an observable entry, stop and failure point."},
    {"method": "risk_reward_and_structure_stop", "score": 9.5, "role": "mandatory", "reason": "Every setup has a predeclared stop and minimum 2.5R target policy."},
    {"method": "trend_continuation_patterns", "score": 8.0, "role": "confirmation", "reason": "Triangles, flags, wedges and rectangles are stronger after trend/context confirmation."},
    {"method": "reversal_patterns", "score": 7.5, "role": "confirmation", "reason": "Double tops/bottoms and head-and-shoulders need neckline break and retest."},
    {"method": "candlestick_confirmation", "score": 7.0, "role": "timing", "reason": "Engulfing and related candles are timing triggers, not standalone direction."},
    {"method": "elliott_wave_plus_fibonacci", "score": 7.0, "role": "context", "reason": "Useful scenario/target context, but alternate counts and subjectivity require confluence."},
    {"method": "rsi_macd_divergence", "score": 7.0, "role": "confirmation", "reason": "Divergence warns of exhaustion; books explicitly reject single-indicator decisions."},
    {"method": "moving_average_regime_filter", "score": 7.0, "role": "filter", "reason": "Separates trend from range; lagging, so it cannot be the entry alone."},
    {"method": "volume_volatility_confirmation", "score": 8.0, "role": "filter", "reason": "Breakout quality and stop distance depend on participation and volatility."},
    {"method": "trailing_channel_and_intermediate_targets", "score": 9.0, "role": "management", "reason": "Protects accrued profit without forcing an early exit."},
)


def method_scores() -> list[dict[str, Any]]:
    """Return immutable policy scores as serializable copies."""
    return [dict(item) for item in METHOD_SCORES]


def _side(bias: str | None) -> str | None:
    if bias == "BULLISH":
        return "long"
    if bias == "BEARISH":
        return "short"
    return None


def _cell(timeframe: str, result: Any) -> dict[str, Any]:
    summary = result.timeframe_summary
    pattern = result.chart_pattern_analysis
    reversal = result.reversal_signals
    fired = [signal.name for signal in result.confirmation_signals if signal.fired]
    active = [item.name for item in (pattern.active_patterns if pattern else [])]
    reversal_types = [item.type for item in (reversal.signals if reversal else [])]
    evidence_count = sum(
        bool(value)
        for value in (
            result.data_quality.status == "OK",
            summary.bias in {"BULLISH", "BEARISH"},
            bool(fired),
            bool(result.confluence_zones),
            bool(result.fibonacci_analysis and result.fibonacci_analysis.validity == "sane"),
            bool(active and active[0] != "ranging"),
            bool(reversal_types),
        )
    )
    quality_score = min(100, evidence_count * 14)
    side = _side(summary.bias)
    if side and active and active[0] in {"uptrend_structure", "downtrend_structure"}:
        setup_type = "continuation_breakout_retest"
    elif side and reversal_types:
        setup_type = "reversal_neckline_retest"
    elif active and active[0] == "ranging":
        setup_type = "range_boundary_reaction"
    else:
        setup_type = "watch"
    blockers: list[str] = []
    if result.data_quality.status != "OK":
        blockers.append("technical_data_degraded")
    if result.key_levels.stop_reference is None:
        blockers.append("missing_structure_stop")
    if result.key_levels.target_reference is None:
        blockers.append("missing_target")
    if not fired:
        blockers.append("confirmation_not_fired")
    return {
        "timeframe": timeframe,
        "setup_type": setup_type,
        "side": side,
        "quality_score": quality_score,
        "bias": summary.bias,
        "pattern": active[0] if active else None,
        "reversal_signals": reversal_types,
        "confirmation_signals": fired,
        "location_confluence": [zone.model_dump(mode="json") for zone in result.confluence_zones],
        "invalidation": {
            "stop_reference": result.key_levels.stop_reference,
            "policy": "structure invalidation or ATR-aware protective stop; never widen risk",
        },
        "target": {
            "target_reference": result.key_levels.target_reference,
            "policy": "measured move/Fibonacci extension only when R:R >= 2.5; otherwise no trade",
        },
        "management": [
            "At first intermediate target, protect only after a new swing confirms.",
            "Trail below/above the latest confirmed channel swing; do not trail from noise.",
            "Close on invalidation, target, opposing confirmed structure, or time-stop.",
        ],
        "blockers": blockers,
        "evidence_only": True,
    }


def build_from_agent(agent: Any) -> dict[str, Any]:
    """Build a multi-timeframe plan from an existing technical agent output."""
    per_tf = getattr(agent, "per_timeframe", {}) or {}
    cells: list[dict[str, Any]] = []
    for key, result in per_tf.items():
        if result is None:
            continue
        timeframe = getattr(result, "timeframe", key)
        cells.append(_cell(timeframe, result))
    order = {"1w": 0, "1d": 1, "4h": 2, "1h": 3, "15m": 4}
    cells.sort(key=lambda item: order.get(item["timeframe"], 99))
    directional = [cell for cell in cells if cell["side"]]
    aligned = bool(directional) and len({cell["side"] for cell in directional}) == 1
    best = max(cells, key=lambda item: item["quality_score"], default=None)
    return {
        "mode": "evidence_only",
        "method_scores": method_scores(),
        "multi_timeframe_alignment": aligned,
        "dominant_side": directional[0]["side"] if aligned else None,
        "entry_policy": "closed-candle confirmation -> level retest -> final RiskGate/economics check",
        "exit_policy": "structure stop + 2.5R target policy + channel/time-stop management",
        "best_timeframe": best["timeframe"] if best else None,
        "cells": cells,
        "promoted_to_decision": False,
    }


def build(view: Any) -> dict[str, Any]:
    """Build a multi-timeframe plan from an existing SymbolAgentView."""
    return build_from_agent(getattr(view, "agent", None))


__all__ = ["METHOD_SCORES", "build", "build_from_agent", "method_scores"]
