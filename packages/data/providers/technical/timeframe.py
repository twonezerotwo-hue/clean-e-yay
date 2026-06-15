"""Per-timeframe technical feature builder (T-MTF) — pure, deterministic, paper-safe.

Packages the pure indicators into one canonical `TechnicalTimeframeResult` for a
single (symbol, closed-candle timeframe). EVIDENCE only:

  * never opens trades, never imports the decision engine / RiskGate;
  * never emits a single aggregated score — `direction_score` and `strength_score`
    stay SEPARATE axes (no "aggregated_technical_score" for all strategies);
  * insufficient / stale data becomes `indicator_quality` + `warnings` diagnostics,
    NEVER a fabricated neutral confidence (DATA_POLICY).

The builder treats `bars` as already-closed candles (closed-candle policy is the
caller's responsibility); it never peeks beyond the bars it is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.data.providers.technical import fibonacci, indicators
from packages.data.registry.loader import load_thresholds
from packages.data.types import (
    ConfirmationSignal,
    FibonacciAnalysis,
    IndicatorQuality,
    IndicatorQualityReport,
    OHLCVBar,
    TechnicalBias,
    TechnicalConfluenceZone,
    TechnicalDataQuality,
    TechnicalKeyLevels,
    TechnicalScoreOverview,
    TechnicalTimeframeResult,
    TechnicalTimeframeSummary,
    TechnicalTrendStrength,
    TfVolatilityRegime,
    Timeframe,
)

# TF bazlı stale eşiği — packages/data/providers/technical/__init__.py ile aynı politika.
STALE_AFTER_SEC: dict[Timeframe, int] = {
    "15m": 1800,
    "1h": 7200,
    "4h": 28800,
    "1d": 172800,
    "1w": 864000,
}
# VWAP yalnızca intraday TF'lerde anlamlıdır (1d/1w'de üretilmez — per-TF semantik).
INTRADAY_TF: frozenset[Timeframe] = frozenset({"15m", "1h", "4h"})
_EMA_PERIODS = (20, 50, 200)


@dataclass(frozen=True)
class TechnicalConfig:
    """thresholds_v1.0.yaml `technical:` bloğundan türetilen deterministik params."""

    bull_cut: float = 60.0
    bear_cut: float = 40.0
    adx_trend_min: float = 20.0
    warmup: dict[str, int] = field(
        default_factory=lambda: {"rsi": 30, "macd": 60, "ema200": 220, "atr": 30, "adx": 40}
    )
    bb_squeeze_pct: float = 4.0
    bb_expansion_pct: float = 12.0
    pivot_left: int = 3
    pivot_right: int = 3
    stop_atr_mult: float = 1.5
    target_rr: float = 2.0


def load_config() -> TechnicalConfig:
    t = load_thresholds().get("technical", {}) or {}
    cuts = t.get("bias_cuts", {}) or {}
    vol = t.get("volatility", {}) or {}
    piv = t.get("swing_pivot", {}) or {}
    warm = t.get("warmup_min_bars", {}) or {}
    return TechnicalConfig(
        bull_cut=float(cuts.get("bull", 60)),
        bear_cut=float(cuts.get("bear", 40)),
        adx_trend_min=float(t.get("adx_trend_min", 20)),
        warmup={
            "rsi": int(warm.get("rsi", 30)),
            "macd": int(warm.get("macd", 60)),
            "ema200": int(warm.get("ema200", 220)),
            "atr": int(warm.get("atr", 30)),
            "adx": int(warm.get("adx", 40)),
        },
        bb_squeeze_pct=float(vol.get("bb_squeeze_pct", 4.0)),
        bb_expansion_pct=float(vol.get("bb_expansion_pct", 12.0)),
        pivot_left=int(piv.get("left", 3)),
        pivot_right=int(piv.get("right", 3)),
        stop_atr_mult=float(t.get("stop_atr_mult", 1.5)),
        target_rr=float(t.get("target_rr", 2.0)),
    )


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _q(ok: bool) -> IndicatorQuality:
    return "OK" if ok else "INSUFFICIENT_HISTORY"


def _ema_stack(emas: list[float | None]) -> str | None:
    if not all(e is not None for e in emas):
        return None
    e20, e50, e200 = emas
    if e20 > e50 > e200:  # type: ignore[operator]
        return "bullish"
    if e20 < e50 < e200:  # type: ignore[operator]
        return "bearish"
    return "mixed"


def _direction_score(
    rsi_v: float | None, macd_norm: float | None, ema_stack: str | None
) -> float | None:
    """0–100 (50 = neutral). None = insufficient evidence — NOT a neutral 50."""
    comps: list[float] = []
    if rsi_v is not None:
        comps.append(_clamp(rsi_v, 0.0, 100.0))
    if macd_norm is not None:
        comps.append(_clamp(50.0 + _clamp(macd_norm, -3.0, 3.0) * (50.0 / 3.0), 0.0, 100.0))
    if ema_stack is not None:
        comps.append({"bullish": 75.0, "bearish": 25.0, "mixed": 50.0}[ema_stack])
    if not comps:
        return None
    return sum(comps) / len(comps)


def _strength_score(adx_v: float | None, direction_score: float | None) -> float | None:
    """0–100 conviction (trend reality + signal alignment). None = insufficient."""
    comps: list[float] = []
    if adx_v is not None:
        comps.append(_clamp(adx_v / 50.0 * 100.0, 0.0, 100.0))
    if direction_score is not None:
        comps.append(_clamp(abs(direction_score - 50.0) * 2.0, 0.0, 100.0))
    if not comps:
        return None
    return sum(comps) / len(comps)


def _bias(direction_score: float | None, cfg: TechnicalConfig) -> TechnicalBias:
    if direction_score is None:
        return "NEUTRAL"
    if direction_score > cfg.bull_cut:
        return "BULLISH"
    if direction_score < cfg.bear_cut:
        return "BEARISH"
    return "NEUTRAL"


def _volatility_regime(
    adx_v: float | None, bb_w: float | None, cfg: TechnicalConfig
) -> TfVolatilityRegime:
    if adx_v is None and bb_w is None:
        return "UNKNOWN"
    if adx_v is not None and adx_v >= cfg.adx_trend_min:
        return "TRENDING"
    if bb_w is not None:
        if bb_w <= cfg.bb_squeeze_pct:
            return "SQUEEZE"
        if bb_w >= cfg.bb_expansion_pct:
            return "EXPANSION"
    return "RANGING"


def _key_levels(
    current: float | None,
    pivots: tuple[list[float], list[float]] | None,
    atr_v: float | None,
    atr_pct: float | None,
    cfg: TechnicalConfig,
) -> TechnicalKeyLevels:
    support = resistance = stop_ref = target_ref = None
    if pivots is not None and current is not None and current > 0:
        highs, lows = pivots
        below = [lvl for lvl in lows if lvl < current]
        above = [hi for hi in highs if hi > current]
        support = max(below) if below else None
        resistance = min(above) if above else None
    if atr_v is not None and current is not None and current > 0:
        # Long-oriented reference (evidence only): nearest support, else ATR buffer.
        base_stop = support if support is not None else current - cfg.stop_atr_mult * atr_v
        if base_stop is not None and base_stop < current:
            stop_ref = base_stop
            risk = current - stop_ref
            if risk > 0:
                target_ref = current + cfg.target_rr * risk
    return TechnicalKeyLevels(
        support=round(support, 6) if support is not None else None,
        resistance=round(resistance, 6) if resistance is not None else None,
        atr=round(atr_v, 6) if atr_v is not None else None,
        atr_percent=round(atr_pct, 4) if atr_pct is not None else None,
        stop_reference=round(stop_ref, 6) if stop_ref is not None else None,
        target_reference=round(target_ref, 6) if target_ref is not None else None,
    )


def _trend_strength(
    adx_t: tuple[float, float, float] | None, cfg: TechnicalConfig
) -> TechnicalTrendStrength:
    if adx_t is None:
        return TechnicalTrendStrength()
    adx_v, plus_di, minus_di = adx_t
    is_tr = adx_v >= cfg.adx_trend_min
    return TechnicalTrendStrength(
        adx=round(adx_v, 2),
        plus_di=round(plus_di, 2),
        minus_di=round(minus_di, 2),
        is_trending=is_tr,
        label="TRENDING" if is_tr else "WEAK",
    )


def _confluence_zones(
    current: float | None,
    atr_pct: float | None,
    support: float | None,
    resistance: float | None,
    vwap_v: float | None,
    fib: FibonacciAnalysis | None,
) -> list[TechnicalConfluenceZone]:
    if current is None or current <= 0:
        return []
    tol_pct = _clamp(atr_pct if atr_pct is not None else 1.0, 0.25, 2.0)
    zones: list[TechnicalConfluenceZone] = []
    for role in ("support", "resistance"):
        comps: list[str] = []
        prices: list[float] = []
        sw = support if role == "support" else resistance
        if sw is not None:
            comps.append(f"swing_{role}")
            prices.append(sw)
        if (
            fib is not None
            and fib.nearest_level is not None
            and fib.nearest_level.role == role
            and fib.nearest_level.price > 0
        ):
            comps.append(f"fib_{fib.nearest_level.label}")
            prices.append(fib.nearest_level.price)
        if vwap_v is not None and vwap_v > 0:
            vrole = "support" if vwap_v <= current else "resistance"
            if vrole == role:
                comps.append("vwap")
                prices.append(vwap_v)
        if len(prices) >= 2:
            anchor = sum(prices) / len(prices)
            if anchor > 0 and all(abs(p - anchor) / anchor * 100.0 <= tol_pct for p in prices):
                zones.append(
                    TechnicalConfluenceZone(
                        price=round(anchor, 6), kind=role, components=comps  # type: ignore[arg-type]
                    )
                )
    return zones


def _confirmations(
    rsi_v: float | None,
    macd_t: tuple[float, float, float] | None,
    ema_stack: str | None,
    current: float | None,
    vwap_v: float | None,
) -> list[ConfirmationSignal]:
    """TIMING gates only (fired/not) — the same magnitude is scored once elsewhere."""
    sigs: list[ConfirmationSignal] = []
    if macd_t is not None:
        hist = macd_t[2]
        sigs.append(
            ConfirmationSignal(
                name="macd_histogram_positive", fired=hist > 0, detail=f"hist={hist:.6f}"
            )
        )
    if rsi_v is not None:
        sigs.append(
            ConfirmationSignal(name="rsi_above_50", fired=rsi_v > 50.0, detail=f"rsi={rsi_v:.1f}")
        )
    if ema_stack is not None:
        sigs.append(
            ConfirmationSignal(
                name="ema_stack_bullish", fired=ema_stack == "bullish", detail=ema_stack
            )
        )
    if vwap_v is not None and current is not None:
        sigs.append(
            ConfirmationSignal(name="above_vwap", fired=current > vwap_v, detail=f"vwap={vwap_v:.4f}")
        )
    return sigs


def build_timeframe_result(
    symbol: str,
    timeframe: Timeframe,
    bars: list[OHLCVBar],
    *,
    now: datetime | None = None,
    config: TechnicalConfig | None = None,
    fibonacci_analysis: FibonacciAnalysis | None = None,
) -> TechnicalTimeframeResult:
    """Build the canonical per-TF technical result from real closed OHLCV bars."""
    now = now or datetime.now(UTC)
    cfg = config or load_config()
    n = len(bars)
    closes = [b.close for b in bars]
    current = closes[-1] if closes else None

    # ── indicators (closed-candle input only) ─────────────────────────────────
    rsi_v = indicators.rsi(closes)
    macd_t = indicators.macd(closes)
    atr_v = indicators.atr(bars)
    atr_pct = indicators.atr_percent(bars)
    adx_t = indicators.adx(bars)
    emas = [indicators.ema(closes, p) for p in _EMA_PERIODS]
    bb_w = indicators.bollinger_width(closes)
    pivots = indicators.swing_pivots(bars, left=cfg.pivot_left, right=cfg.pivot_right)
    vwap_v = indicators.vwap(bars) if timeframe in INTRADAY_TF else None

    macd_norm = macd_t[2] / current * 100.0 if (macd_t is not None and current and current > 0) else None
    ema_stack = _ema_stack(emas)
    adx_v = adx_t[0] if adx_t is not None else None

    # ── data quality / warm-up (insufficient = diagnostic, never fake value) ───
    iq = IndicatorQualityReport(
        rsi=_q(rsi_v is not None and n >= cfg.warmup["rsi"]),
        macd=_q(macd_norm is not None and n >= cfg.warmup["macd"]),
        ema200=_q(emas[2] is not None and n >= cfg.warmup["ema200"]),
        atr=_q(atr_v is not None and n >= cfg.warmup["atr"]),
        adx=_q(adx_t is not None and n >= cfg.warmup["adx"]),
    )
    stale = bool(bars) and (
        (now - bars[-1].ts).total_seconds() > STALE_AFTER_SEC.get(timeframe, 172800)
    )
    warnings: list[str] = []
    if not bars:
        warnings.append("no_bars")
    if stale:
        warnings.append("stale_last_bar")
    for name, q in (
        ("rsi", iq.rsi), ("macd", iq.macd), ("ema200", iq.ema200), ("atr", iq.atr), ("adx", iq.adx)
    ):
        if q == "INSUFFICIENT_HISTORY":
            warnings.append(f"insufficient_history:{name}")
    core_ok = iq.rsi == "OK" and iq.atr == "OK"
    status = "OK" if (bars and not stale and core_ok) else "DEGRADED"

    # ── fibonacci (per-TF semantics: only 1D / 4H) ────────────────────────────
    fib = fibonacci_analysis
    if fib is None and timeframe in ("4h", "1d"):
        fib = fibonacci.analyze(
            bars, timeframe=("1D" if timeframe == "1d" else "4H"), current_price=current
        )

    # ── scoring (SEPARATE axes) + summary ─────────────────────────────────────
    direction = _direction_score(rsi_v, macd_norm, ema_stack)
    strength = _strength_score(adx_v, direction)
    bias = _bias(direction, cfg)
    key_levels = _key_levels(current, pivots, atr_v, atr_pct, cfg)
    trend = _trend_strength(adx_t, cfg)
    vol_regime = _volatility_regime(adx_v, bb_w, cfg)
    zones = _confluence_zones(
        current, atr_pct, key_levels.support, key_levels.resistance, vwap_v, fib
    )

    evidence: list[str] = []
    if direction is not None:
        evidence.append(f"direction_score={direction:.1f}")
    else:
        evidence.append("direction_unavailable_insufficient_data")
    if trend.label != "UNKNOWN":
        evidence.append(f"adx={trend.adx} ({trend.label})")
    evidence.append(f"volatility_regime={vol_regime}")
    if fib is not None and fib.validity != "unavailable":
        evidence.append(f"fib_zone={fib.zone}")
    for z in zones:
        evidence.append(f"confluence:{z.kind}@{z.price} [{'+'.join(z.components)}]")

    summary = TechnicalTimeframeSummary(bias=bias, evidence=evidence, warnings=warnings)

    return TechnicalTimeframeResult(
        symbol=symbol,
        timeframe=timeframe,
        data_quality=TechnicalDataQuality(
            status=status, bars_used=n, stale=stale, indicator_quality=iq, warnings=warnings
        ),
        score_overview=TechnicalScoreOverview(
            direction_score=round(direction, 2) if direction is not None else None,
            strength_score=round(strength, 2) if strength is not None else None,
        ),
        key_levels=key_levels,
        confirmation_signals=_confirmations(rsi_v, macd_t, ema_stack, current, vwap_v),
        trend_strength=trend,
        volatility_regime=vol_regime,
        confluence_zones=zones,
        timeframe_summary=summary,
        fibonacci_analysis=fib,
        status=status,
        source=bars[-1].source if bars else "none",
        ts=bars[-1].ts if bars else now,
    )
