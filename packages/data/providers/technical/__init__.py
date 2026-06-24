"""Teknik analiz sağlayıcısı — gerçek OHLCV barlarından hesaplar (T1).

Mock/hash sinyal üretimi kaldırıldı. Bar yoksa/yetersizse indikatör
alanları None kalır ve snapshot `status="DEGRADED"` işaretlenir; score
nötr (50) döner — uydurma değer yok (DATA_POLICY).

TF bazlı freshness: son bar TF'e göre eskiyse DEGRADED:
15m > 30dk, 1h > 2sa, 4h > 8sa, 1d > 48sa, 1w > 10g.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.data.providers import ohlcv
from packages.data.providers.technical import fibonacci, indicators
from packages.data.types import (
    TIMEFRAMES,
    FibonacciAnalysis,
    OHLCVBar,
    TechnicalInsight,
    TechnicalSnapshot,
    Timeframe,
)

# TF bazlı stale eşiği (saniye) — 15m hızlı bayatlar, 1w en toleranslı.
STALE_AFTER_SEC: dict[Timeframe, int] = {
    "15m": 1800,        # 30 dk
    "1h": 7200,         # 2 sa
    "4h": 28800,        # 8 sa
    "1d": 172800,       # 48 sa
    "1w": 864000,       # 10 g
}

_EMA_PERIODS = (20, 50, 200)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_snapshot(
    symbol: str,
    timeframe: Timeframe,
    bars: list[OHLCVBar],
    *,
    now: datetime | None = None,
) -> TechnicalSnapshot:
    """Saf hesap: barlardan TechnicalSnapshot üretir (network yok)."""
    now = now or datetime.now(UTC)
    closes = [b.close for b in bars]
    rsi_v = indicators.rsi(closes)
    macd_t = indicators.macd(closes)
    atr_v = indicators.atr(bars)
    emas = [indicators.ema(closes, p) for p in _EMA_PERIODS]

    ema_stack = None
    if all(e is not None for e in emas):
        e20, e50, e200 = emas
        if e20 > e50 > e200:  # type: ignore[operator]
            ema_stack = "bullish"
        elif e20 < e50 < e200:  # type: ignore[operator]
            ema_stack = "bearish"
        else:
            ema_stack = "mixed"

    macd_norm = None
    if macd_t is not None and closes and closes[-1] > 0:
        macd_norm = macd_t[2] / closes[-1] * 100.0

    score = 50.0
    if rsi_v is not None:
        score += (rsi_v - 50.0) * 0.6
    if macd_norm is not None:
        score += _clamp(macd_norm, -3.0, 3.0) * 5.0
    score = _clamp(score, 0.0, 100.0)

    # Top-down GATED direction (the score the decision engine actually consumes via
    # consensus `_touche`): momentum trigger gated by location/pattern/volume evidence.
    # Lazy import avoids a package-init cycle (timeframe imports sibling submodules).
    from packages.data.providers.technical.timeframe import build_timeframe_result

    tf_result = build_timeframe_result(symbol, timeframe, bars, now=now)
    direction_score = tf_result.score_overview.direction_score
    location_gate = tf_result.score_overview.location_gate_multiplier
    # Compact location evidence (the "where am I" read behind the gate) — fib zone,
    # confluence, chart pattern, reversal. Surfaced for LLM narration / fallback.
    _LOC_PREFIXES = ("fib_zone=", "reversal_bias=", "pattern=", "confluence:")
    location_evidence = [
        e for e in tf_result.timeframe_summary.evidence if e.startswith(_LOC_PREFIXES)
    ][:3]

    stale = bool(bars) and (
        (now - bars[-1].ts).total_seconds() > STALE_AFTER_SEC[timeframe]
    )
    degraded = (
        not bars
        or stale
        or rsi_v is None
        or macd_norm is None
        or atr_v is None
        or ema_stack is None
    )
    return TechnicalSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        rsi=round(rsi_v, 2) if rsi_v is not None else None,
        macd=round(macd_norm, 3) if macd_norm is not None else None,
        atr=round(atr_v, 4) if atr_v is not None else None,
        ema_stack=ema_stack,  # type: ignore[arg-type]
        score=round(score, 2),
        direction_score=round(direction_score, 2) if direction_score is not None else None,
        location_gate=round(location_gate, 3) if location_gate is not None else None,
        location_evidence=location_evidence,
        ts=bars[-1].ts if bars else now,
        status="DEGRADED" if degraded else "OK",
        source=bars[-1].source if bars else "none",
        bars_used=len(bars),
    )


def get_snapshot(symbol: str, timeframe: str = "1d") -> TechnicalSnapshot:
    tf: Timeframe = timeframe if timeframe in TIMEFRAMES else "1d"  # type: ignore[assignment]
    bars = ohlcv.get_bars(symbol, tf)
    return compute_snapshot(symbol, tf, bars)


# ── F1 — Multi-timeframe Fibonacci (additive technical evidence) ──────────────
# Does NOT change `technical_score` (compute_snapshot is untouched), does NOT open
# trades, and is NOT consumed by the decision engine / RiskGate.

def _momentum_agrees(zone: str, snap: TechnicalSnapshot) -> bool:
    """Whether 1D momentum agrees with a confluence support/resistance zone.

    Reuses the existing snapshot signals (ema_stack / RSI / MACD) — read-only; it
    does not recompute or alter `technical_score`.
    """
    bullish = (
        snap.ema_stack == "bullish"
        or (snap.rsi is not None and snap.rsi >= 55)
        or (snap.macd is not None and snap.macd > 0)
    )
    bearish = (
        snap.ema_stack == "bearish"
        or (snap.rsi is not None and snap.rsi <= 45)
        or (snap.macd is not None and snap.macd < 0)
    )
    if zone == "support":
        return bool(bullish)
    if zone == "resistance":
        return bool(bearish)
    return False


def get_technical_insight(symbol: str, *, now: datetime | None = None) -> TechnicalInsight:
    """1D (HTF swing context) + 4H (retest context) Fibonacci evidence for a symbol.

    Uses cache-backed OHLCV (the pipeline already warms 1d/4h). If 4H bars are
    unavailable, 1D analysis is kept and 4H is marked unavailable (no invented
    levels). Never trades, never touches RiskGate.
    """
    bars_1d = ohlcv.get_bars(symbol, "1d")
    bars_4h = ohlcv.get_bars(symbol, "4h")

    current: float | None = None
    if bars_4h:
        current = bars_4h[-1].close
    elif bars_1d:
        current = bars_1d[-1].close

    fib_1d = fibonacci.analyze(bars_1d, timeframe="1D", current_price=current)
    if bars_4h:
        fib_4h = fibonacci.analyze(bars_4h, timeframe="4H", current_price=current)
    else:
        fib_4h = FibonacciAnalysis(
            timeframe="4H", validity="unavailable", diagnostics=["bars_4h_unavailable"]
        )

    atr_4h = indicators.atr(bars_4h) if bars_4h else None
    atr_pct = (atr_4h / current * 100.0) if (atr_4h and current and current > 0) else None
    conf = fibonacci.confluence(fib_1d, fib_4h, current_price=current or 0.0, atr_pct=atr_pct)

    snap_1d = compute_snapshot(symbol, "1d", bars_1d, now=now)
    momentum_ok = _momentum_agrees(conf.confluence_zone, snap_1d)
    score = fibonacci.fibonacci_score(fib_1d, fib_4h, conf, momentum_ok=momentum_ok)

    return TechnicalInsight(
        symbol=symbol,
        fib_1d=fib_1d,
        fib_4h=fib_4h,
        fib_confluence=conf,
        fibonacci_score=score,
    )
