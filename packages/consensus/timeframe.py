"""Cross-timeframe consensus (T2) — pure, deterministic, paper-safe.

Aggregates per-timeframe `TechnicalTimeframeResult` features into one asset-level
`ConsensusSnapshot`. EVIDENCE only — never opens trades, never sizes, not the
RiskGate. Core rules from the architecture:

  * SEPARATE axes — direction / strength / agreement / alignment are distinct;
    there is NO single collapsed score for all strategies.
  * NEUTRAL biases DILUTE alignment (they are not forced into bull/bear).
  * Countertrend is CONDITIONAL: only when the higher-TF bias and the lower-TF
    signal disagree in sign (same direction = trend-aligned, NOT countertrend).
  * Degraded/insufficient timeframes are blocking diagnostics, never fake reads.

The strategy-specific timeframe weighting (config/weights_v1.0.yaml tf_weights)
is a downstream decision-layer concern; here weighting defaults to equal and is
overridable via `tf_weights` so the layer stays strategy-agnostic.
"""
from __future__ import annotations

from packages.data.types import (
    ConsensusSnapshot,
    CrossTimeframeConfluenceZone,
    TechnicalTimeframeResult,
    Timeframe,
)

_TF_KEY: dict[Timeframe, str] = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}
_TF_RANK: dict[Timeframe, int] = {"15m": 0, "1h": 1, "4h": 2, "1d": 3, "1w": 4}
_SIGN: dict[str, int] = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0}

_ALIGNED_MIN = 60.0          # alignment_score ≥ → ALIGNED (when unanimous)
_CONFLUENCE_TOL_PCT = 1.0    # cross-TF level clustering tolerance (% of price)


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """pairs: list of (value, weight). None if no positive weight."""
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in pairs) / total_w


def _cross_confluence(
    valid: list[tuple[Timeframe, TechnicalTimeframeResult]], tol_pct: float
) -> list[CrossTimeframeConfluenceZone]:
    cand: list[tuple[float, str, str, str]] = []  # (price, kind, tf_key, label)
    for t, r in valid:
        key = _TF_KEY[t]
        if r.key_levels.support is not None:
            cand.append((r.key_levels.support, "support", key, "swing_support"))
        if r.key_levels.resistance is not None:
            cand.append((r.key_levels.resistance, "resistance", key, "swing_resistance"))
        fib = r.fibonacci_analysis
        if (
            fib is not None
            and fib.nearest_level is not None
            and fib.nearest_level.role in ("support", "resistance")
            and fib.nearest_level.price > 0
        ):
            cand.append(
                (fib.nearest_level.price, fib.nearest_level.role, key, f"fib_{fib.nearest_level.label}")
            )

    zones: list[CrossTimeframeConfluenceZone] = []
    for kind in ("support", "resistance"):
        items = sorted((c for c in cand if c[1] == kind), key=lambda c: c[0])
        used = [False] * len(items)
        for i, item in enumerate(items):
            if used[i]:
                continue
            anchor = item[0]
            group = [item]
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j] or anchor <= 0:
                    continue
                if abs(items[j][0] - anchor) / anchor * 100.0 <= tol_pct:
                    group.append(items[j])
                    used[j] = True
            tfs = sorted({g[2] for g in group})
            if len(tfs) >= 2:  # cross-TF requires ≥2 distinct timeframes
                price = sum(g[0] for g in group) / len(group)
                comps = sorted({g[3] for g in group})
                zones.append(
                    CrossTimeframeConfluenceZone(
                        price=round(price, 6), kind=kind, timeframes=tfs, components=comps  # type: ignore[arg-type]
                    )
                )
    return zones


def build_consensus(
    asset: str,
    per_tf: dict[Timeframe, TechnicalTimeframeResult],
    *,
    tf_weights: dict[Timeframe, float] | None = None,
    confluence_tol_pct: float = _CONFLUENCE_TOL_PCT,
) -> ConsensusSnapshot:
    """Build a cross-timeframe ConsensusSnapshot from per-TF technical results."""
    per_timeframe_bias = {_TF_KEY[t]: r.timeframe_summary.bias for t, r in per_tf.items() if t in _TF_KEY}

    valid: list[tuple[Timeframe, TechnicalTimeframeResult]] = []
    blocking = confirmed = pending = 0
    for t, r in per_tf.items():
        if t not in _TF_KEY:
            continue
        if r.data_quality.status == "DEGRADED" or r.score_overview.direction_score is None:
            blocking += 1
            continue
        valid.append((t, r))
        bias = r.timeframe_summary.bias
        if bias != "NEUTRAL":
            if any(s.fired for s in r.confirmation_signals):
                confirmed += 1
            else:
                pending += 1

    def _w(t: Timeframe) -> float:
        return float(tf_weights.get(t, 1.0)) if tf_weights is not None else 1.0

    direction = _weighted_mean(
        [(r.score_overview.direction_score, _w(t)) for t, r in valid if r.score_overview.direction_score is not None]
    )
    strength = _weighted_mean(
        [(r.score_overview.strength_score, _w(t)) for t, r in valid if r.score_overview.strength_score is not None]
    )

    # alignment_score: weighted directional consensus magnitude (NEUTRAL → 0 → dilutes).
    net = _weighted_mean([(float(_SIGN[r.timeframe_summary.bias]), _w(t)) for t, r in valid])
    alignment_score = round(abs(net) * 100.0, 1) if net is not None else 0.0

    # agreement_score: unanimity among DIRECTIONAL (non-neutral) timeframes only.
    directional = [(t, _SIGN[r.timeframe_summary.bias]) for t, r in valid if _SIGN[r.timeframe_summary.bias] != 0]
    bull = sum(1 for _, s in directional if s > 0)
    bear = sum(1 for _, s in directional if s < 0)
    agreement_score = round(max(bull, bear) / len(directional) * 100.0, 1) if directional else 0.0

    # Conditional countertrend: higher-TF bias vs lower-TF signal disagree in sign.
    is_countertrend = False
    if len(directional) >= 2:
        higher_t, higher_s = max(directional, key=lambda kv: _TF_RANK[kv[0]])
        lower_t, lower_s = min(directional, key=lambda kv: _TF_RANK[kv[0]])
        if higher_t != lower_t and higher_s != lower_s:
            is_countertrend = True

    has_conflict = bull > 0 and bear > 0
    if is_countertrend:
        alignment_status = "COUNTERTREND"
    elif has_conflict:
        alignment_status = "CONFLICTED"
    elif directional and agreement_score >= 100.0 and alignment_score >= _ALIGNED_MIN:
        alignment_status = "ALIGNED"
    else:
        alignment_status = "PARTIAL"

    cross_conf = _cross_confluence(valid, confluence_tol_pct)

    evidence: list[str] = []
    evidence.append(f"valid_tfs={len(valid)} blocking={blocking}")
    if direction is not None:
        evidence.append(f"direction_score={direction:.1f} strength={strength:.1f}" if strength is not None
                        else f"direction_score={direction:.1f}")
    evidence.append(f"alignment={alignment_status} ({alignment_score:.0f}) agreement={agreement_score:.0f}")
    if is_countertrend:
        evidence.append(f"countertrend: {_TF_KEY[higher_t]} vs {_TF_KEY[lower_t]} disagree")
    for z in cross_conf:
        evidence.append(f"cross_confluence:{z.kind}@{z.price} [{'+'.join(z.timeframes)}]")

    return ConsensusSnapshot(
        asset=asset,
        per_timeframe_bias=per_timeframe_bias,
        alignment_status=alignment_status,  # type: ignore[arg-type]
        alignment_score=alignment_score,
        cross_timeframe_confluence=cross_conf,
        direction_score=round(direction, 2) if direction is not None else None,
        strength_score=round(strength, 2) if strength is not None else None,
        agreement_score=agreement_score,
        is_countertrend=is_countertrend,
        confirmed_count=confirmed,
        pending_count=pending,
        blocking_count=blocking,
        evidence=evidence,
    )
