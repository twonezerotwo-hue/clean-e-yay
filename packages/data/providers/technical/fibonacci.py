"""Multi-timeframe Fibonacci analysis (F1) — pure, deterministic, paper-safe.

Technical EVIDENCE only. Computes swing-based retracement/extension levels, zone
classification, and 1D/4H confluence from real OHLCV bars. It never opens trades,
never imports the decision engine / RiskGate, and never changes `technical_score`.
Missing / insufficient / invalid data becomes diagnostics — no fabricated levels.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.providers.technical.indicators import atr as _atr
from packages.data.types import (
    FibonacciAnalysis,
    FibonacciConfluence,
    FibonacciLevel,
    FibTF,
    OHLCVBar,
)

RETRACEMENTS: tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786)
EXTENSIONS: tuple[float, ...] = (1.272, 1.618)


@dataclass(frozen=True)
class FibonacciConfig:
    """Deterministic Fibonacci params — kept out of the math (provider config)."""

    lookback_bars: int = 120
    min_bars: int = 20
    min_swing_pct: float = 1.0           # swing range must be ≥ this % of price
    fallback_proximity_pct: float = 1.5  # zone proximity when ATR% unavailable
    neutral_eps: float = 0.0015          # |level-current|/current ≤ this → neutral
    retracements: tuple[float, ...] = RETRACEMENTS
    extensions: tuple[float, ...] = EXTENSIONS


# 1D = higher-timeframe swing context; 4H = shorter-term retest context.
CONFIG_1D = FibonacciConfig(lookback_bars=120, fallback_proximity_pct=1.5)
CONFIG_4H = FibonacciConfig(lookback_bars=120, fallback_proximity_pct=0.75)


def _role(price: float, current: float, neutral_eps: float) -> str:
    if current <= 0:
        return "unknown"
    diff = (price - current) / current
    if abs(diff) <= neutral_eps:
        return "neutral"
    return "support" if price < current else "resistance"


def _level(ratio: float, price: float, kind: str, current: float, cfg: FibonacciConfig) -> FibonacciLevel:
    dist = abs(price - current) / current * 100 if current > 0 else None
    return FibonacciLevel(
        ratio=round(ratio, 3),
        label=f"{ratio * 100:g}%",
        price=round(price, 6),
        kind=kind,  # type: ignore[arg-type]
        role=_role(price, current, cfg.neutral_eps),  # type: ignore[arg-type]
        distance_pct=round(dist, 4) if dist is not None else None,
    )


def _build_levels(
    swing_high: float, swing_low: float, current: float, trend: str, cfg: FibonacciConfig
) -> list[FibonacciLevel]:
    rng = swing_high - swing_low
    out: list[FibonacciLevel] = []
    for r in cfg.retracements:
        # uptrend/range: pull back down from the high; downtrend: bounce up from the low.
        price = (swing_low + r * rng) if trend == "downtrend" else (swing_high - r * rng)
        out.append(_level(r, price, "retracement", current, cfg))
    if trend in ("uptrend", "downtrend"):
        for r in cfg.extensions:
            # uptrend: project above the high; downtrend: project below the low.
            price = (swing_high - r * rng) if trend == "downtrend" else (swing_low + r * rng)
            out.append(_level(r, price, "extension", current, cfg))
    # Sanity: Fibonacci prices must be positive — never emit a non-positive level.
    return [lvl for lvl in out if lvl.price > 0]


def _zone(
    current: float,
    swing_high: float,
    swing_low: float,
    nearest: FibonacciLevel | None,
    proximity_pct: float,
) -> str:
    if current > swing_high:
        return "breakout"
    if current < swing_low:
        return "breakdown"
    if nearest is not None and nearest.distance_pct is not None and nearest.distance_pct <= proximity_pct:
        if nearest.role == "support":
            return "near_support"
        if nearest.role == "resistance":
            return "near_resistance"
    return "mid_range"


def analyze(
    bars: list[OHLCVBar],
    *,
    timeframe: FibTF,
    current_price: float | None = None,
    config: FibonacciConfig | None = None,
) -> FibonacciAnalysis:
    """Deterministic Fibonacci analysis for one timeframe from real OHLCV bars."""
    cfg = config or (CONFIG_1D if timeframe == "1D" else CONFIG_4H)
    diag: list[str] = []

    if not bars or len(bars) < cfg.min_bars:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return FibonacciAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    window = bars[-cfg.lookback_bars :]
    current = current_price if current_price is not None else window[-1].close
    if current is None or current <= 0:
        diag.append("invalid_current_price")
        return FibonacciAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    highs = [b.high for b in window]
    lows = [b.low for b in window]
    hi_idx = max(range(len(window)), key=lambda i: highs[i])
    lo_idx = min(range(len(window)), key=lambda i: lows[i])
    swing_high, swing_low = highs[hi_idx], lows[lo_idx]

    if swing_high <= 0 or swing_low <= 0 or swing_high <= swing_low:
        diag.append("invalid_swing")
        return FibonacciAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    midpoint = (swing_high + swing_low) / 2.0
    if lo_idx < hi_idx and current > midpoint:
        trend = "uptrend"
    elif hi_idx < lo_idx and current < midpoint:
        trend = "downtrend"
    else:
        trend = "range"
    swing_start = window[min(hi_idx, lo_idx)].ts.isoformat()
    swing_end = window[max(hi_idx, lo_idx)].ts.isoformat()

    swing_pct = (swing_high - swing_low) / current * 100.0
    if swing_pct < cfg.min_swing_pct:
        diag.append(f"swing_range_too_small:{swing_pct:.2f}pct")
        return FibonacciAnalysis(
            timeframe=timeframe,
            swing_high=round(swing_high, 6),
            swing_low=round(swing_low, 6),
            swing_start=swing_start,
            swing_end=swing_end,
            trend_direction=trend,  # type: ignore[arg-type]
            validity="weak",
            diagnostics=diag,  # no fabricated levels
        )

    levels = _build_levels(swing_high, swing_low, current, trend, cfg)
    nearest = min(levels, key=lambda lvl: lvl.distance_pct or 0.0) if levels else None
    nearest_dist = nearest.distance_pct if nearest else None

    atr_v = _atr(window)
    atr_pct = (atr_v / current * 100.0) if atr_v else None
    proximity = atr_pct if atr_pct is not None else cfg.fallback_proximity_pct
    zone = _zone(current, swing_high, swing_low, nearest, proximity)

    return FibonacciAnalysis(
        timeframe=timeframe,
        swing_high=round(swing_high, 6),
        swing_low=round(swing_low, 6),
        swing_start=swing_start,
        swing_end=swing_end,
        trend_direction=trend,  # type: ignore[arg-type]
        levels=levels,
        nearest_level=nearest,
        nearest_distance_pct=round(nearest_dist, 4) if nearest_dist is not None else None,
        zone=zone,  # type: ignore[arg-type]
        validity="sane",
        diagnostics=diag,
    )


def confluence(
    fib_1d: FibonacciAnalysis | None,
    fib_4h: FibonacciAnalysis | None,
    *,
    current_price: float,
    atr_pct: float | None = None,
) -> FibonacciConfluence:
    """1D/4H level alignment — restrictive, presentation-only (never invents levels)."""
    if fib_1d is None or fib_4h is None:
        return FibonacciConfluence(
            confluence_zone="unknown", reason="missing analysis", diagnostics=["missing_analysis"]
        )
    n1, n4 = fib_1d.nearest_level, fib_4h.nearest_level
    if (
        fib_1d.validity == "unavailable"
        or fib_4h.validity == "unavailable"
        or n1 is None
        or n4 is None
    ):
        return FibonacciConfluence(
            confluence_zone="none",
            nearest_1d_level=n1,
            nearest_4h_level=n4,
            reason="no confluence — incomplete levels",
            diagnostics=["nearest_level_unavailable"],
        )
    if current_price <= 0:
        return FibonacciConfluence(
            confluence_zone="unknown",
            reason="invalid price",
            diagnostics=["invalid_current_price"],
        )

    dist = abs(n1.price - n4.price) / current_price * 100.0
    threshold = max(0.5, min(2.0, atr_pct if atr_pct is not None else 1.0))
    has = dist <= threshold
    if not has:
        zone, score, reason = "none", 0, f"levels {dist:.2f}% apart > {threshold:.2f}% threshold"
    elif n1.role == "support" and n4.role == "support":
        zone, score, reason = "support", 20, "1D+4H support confluence"
    elif n1.role == "resistance" and n4.role == "resistance":
        zone, score, reason = "resistance", 20, "1D+4H resistance confluence"
    else:
        zone, score, reason = "mixed", 10, "1D/4H mixed support/resistance"

    return FibonacciConfluence(
        has_confluence=has,
        confluence_zone=zone,  # type: ignore[arg-type]
        nearest_1d_level=n1,
        nearest_4h_level=n4,
        distance_between_levels_pct=round(dist, 4),
        score=score,
        reason=reason,
        diagnostics=[],
    )


def fibonacci_score(
    fib_1d: FibonacciAnalysis | None,
    fib_4h: FibonacciAnalysis | None,
    conf: FibonacciConfluence | None,
    *,
    momentum_ok: bool = False,
) -> int:
    """Map the Fibonacci evidence to a 0–25 score (never above 25). Evidence only —
    not consumed by the decision engine / RiskGate, so it can't enable a trade."""
    if fib_1d is None or fib_1d.validity == "unavailable":
        return 0
    if conf is not None and conf.has_confluence and conf.confluence_zone in ("support", "resistance"):
        return 25 if momentum_ok else 20
    if conf is not None and conf.confluence_zone == "mixed":
        return 5
    if fib_1d.validity == "weak":
        return 5
    near = fib_1d.zone in ("near_support", "near_resistance")
    if fib_4h is not None and fib_4h.zone in ("near_support", "near_resistance"):
        near = True
    if near:
        return 15
    if fib_1d.zone == "mid_range":
        return 10
    return 10
