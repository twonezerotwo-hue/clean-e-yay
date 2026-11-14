"""Paper position sizing — deterministic base → USD notional, with a hard no-AI-boost
invariant.

Rules (non-negotiable):
- The deterministic consensus/regime/risk pipeline (decision engine) computes the base
  `size_multiplier`. That base may reflect conviction strength (stronger consensus →
  larger deterministic base, up to MAX_SIZE_MULTIPLIER).
- AI / opinion / persona / conviction(LLM) / learning multipliers may ONLY reduce size.
  Any such multiplier is clamped to ≤ 1.0 here (`clamp_ai_multiplier`); they can never
  increase a position. AI may reduce, block, warn, or route to manual review — never boost.
- Sizing only produces a number. It does NOT bypass RiskGate / DQS / KillSwitch / halt /
  manual-ready / price-sanity / state-anomaly — those gates still apply at open time
  (decision engine, attempt_open, manual_queue.approve). RiskGate remains final.
"""
from __future__ import annotations

from packages.data.numeric import bounded, is_finite
from packages.data.registry.loader import load_thresholds

# Deterministic conviction ceiling for the consensus base multiplier. Nothing —
# deterministic or AI — may size above this.
MAX_SIZE_MULTIPLIER = 1.5


def clamp_ai_multiplier(multiplier: float | None) -> float:
    """AI/opinion/persona/conviction multipliers may only reduce → clamp to [0.0, 1.0].

    `None` (no opinion) is neutral (1.0). A value > 1.0 (an attempted boost) becomes
    exactly 1.0 — AI can never increase size. A non-finite opinion (NaN/inf) is a
    broken input, not an opinion: it reduces to 0.0 (no position).
    """
    if multiplier is None:
        return 1.0
    return bounded(multiplier, 0.0, 1.0, default=0.0)


def apply_ai_opinion(base_multiplier: float, ai_multiplier: float | None) -> float:
    """Combine a deterministic base multiplier with an AI opinion that may only reduce.

    Returns `base × clamp_ai_multiplier(ai)`. With ai > 1.0 the result equals the base
    (no boost); with ai < 1.0 the base is reduced.
    """
    base = float(base_multiplier) if is_finite(base_multiplier) else 0.0
    return max(0.0, base) * clamp_ai_multiplier(ai_multiplier)


def _max_position_usd() -> float:
    return float(load_thresholds()["paper_trading"]["max_position_usd"])


def compute_size_usd(
    size_multiplier: float,
    *,
    max_position_usd: float | None = None,
) -> float:
    """Final paper notional from a (deterministic) size multiplier.

    The multiplier is floored at 0 and capped at MAX_SIZE_MULTIPLIER, then scaled by
    the configured max position notional. Never negative, never above the cap.

    A non-finite multiplier or cap (NaN/inf) yields 0.0: a broken sizing input must
    never open a position. (`max(0, min(1.5, NaN))` used to return 1.5 — the largest
    position — because every comparison with NaN is false.)
    """
    cap = max_position_usd if max_position_usd is not None else _max_position_usd()
    if not is_finite(cap) or not is_finite(size_multiplier):
        return 0.0
    m = bounded(size_multiplier, 0.0, MAX_SIZE_MULTIPLIER, default=0.0)
    return round(max(0.0, float(cap)) * m, 2)
