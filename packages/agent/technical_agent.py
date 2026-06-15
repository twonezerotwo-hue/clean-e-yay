"""TechnicalAgent — one structured technical opinion per symbol (T2).

Consumes per-timeframe `TechnicalTimeframeResult` features and produces a single
structured agent view: a stance (ALLOW / CAUTION / ABSTAIN / DEGRADED), coarse
direction/strength summaries (per-TF detail stays authoritative), an invalidation
reference, and an explicit `missing_data` list.

Deterministic and paper-safe: it NEVER opens trades, NEVER sizes positions, and
is NOT the RiskGate. Missing / degraded inputs become ABSTAIN / DEGRADED +
missing_data diagnostics — never a fabricated confident opinion (DATA_POLICY).
"""
from __future__ import annotations

from packages.data.types import (
    TechnicalAgentOutput,
    TechnicalInvalidation,
    TechnicalTimeframeResult,
    Timeframe,
)

# Contract-naming for the per_timeframe map.
_TF_KEY: dict[Timeframe, str] = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}
# Üst TF daha güvenilir bağlam → invalidation/observation tercih sırası.
_PRIORITY: tuple[Timeframe, ...] = ("1d", "4h", "1h", "15m", "1w")
_STRENGTH_FLOOR = 30.0


def evaluate(
    symbol: str,
    per_tf: dict[Timeframe, TechnicalTimeframeResult],
) -> TechnicalAgentOutput:
    """Build one structured technical opinion from per-timeframe results."""
    per_timeframe = {_TF_KEY[t]: r for t, r in per_tf.items() if t in _TF_KEY}

    valid: list[tuple[Timeframe, TechnicalTimeframeResult]] = []
    missing: list[str] = []
    degraded = 0
    for t, r in per_tf.items():
        ds = r.score_overview.direction_score
        if r.data_quality.status == "DEGRADED" or ds is None:
            degraded += 1
            missing.append(_TF_KEY.get(t, str(t)))
        else:
            valid.append((t, r))

    if not valid:
        return TechnicalAgentOutput(
            symbol=symbol,
            per_timeframe=per_timeframe,
            stance="ABSTAIN",
            missing_data=sorted(missing) or ["no_timeframes"],
            used_observations=["no usable timeframe (insufficient/degraded data)"],
        )

    # Coarse summaries (equal weight) — per_timeframe stays authoritative; the
    # strategy-specific weighting happens in consensus, not here.
    dirs = [r.score_overview.direction_score for _, r in valid]
    strs = [r.score_overview.strength_score for _, r in valid if r.score_overview.strength_score is not None]
    direction = sum(dirs) / len(dirs)
    strength = sum(strs) / len(strs) if strs else None

    biases = {r.timeframe_summary.bias for _, r in valid}
    conflict = "BULLISH" in biases and "BEARISH" in biases

    if degraded > len(valid):
        stance = "DEGRADED"
    elif conflict or (strength is not None and strength < _STRENGTH_FLOOR):
        stance = "CAUTION"
    elif biases == {"NEUTRAL"}:
        stance = "ABSTAIN"
    else:
        stance = "ALLOW"

    valid_by_tf = dict(valid)
    invalidation: TechnicalInvalidation | None = None
    for t in _PRIORITY:
        r = valid_by_tf.get(t)
        if r is not None and r.key_levels.stop_reference is not None:
            invalidation = TechnicalInvalidation(
                timeframe=t,
                price=r.key_levels.stop_reference,
                reason=f"{_TF_KEY[t]} stop reference ({r.timeframe_summary.bias} bias) broken",
            )
            break

    observations: list[str] = []
    for t, r in sorted(valid, key=lambda kv: _PRIORITY.index(kv[0]) if kv[0] in _PRIORITY else 99):
        observations.append(
            f"{_TF_KEY[t]}: {r.timeframe_summary.bias} dir={r.score_overview.direction_score} "
            f"adx={r.trend_strength.adx} regime={r.volatility_regime}"
        )

    return TechnicalAgentOutput(
        symbol=symbol,
        per_timeframe=per_timeframe,
        stance=stance,
        direction_score=round(direction, 2),
        strength_score=round(strength, 2) if strength is not None else None,
        used_observations=observations,
        invalidation=invalidation,
        missing_data=sorted(missing),
    )
