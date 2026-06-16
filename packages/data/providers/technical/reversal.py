"""Reversal-signal detection (section 4.5) — momentum divergence + double formations.

Pure functions over closed OHLCV bars. EVIDENCE only: a detected reversal never opens
a trade, never feeds a single aggregate score, and is not the RiskGate. Insufficient
history → None (the field is absent, never a fabricated NEUTRAL — DATA_POLICY).

Divergence is read on the last two swing pivots: a higher price high with a lower
oscillator high is bearish; a lower price low with a higher oscillator low is bullish.
A double bottom/top is two similar lows/highs separated by an opposite pivot.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.types import OHLCVBar, ReversalSignal, TechnicalReversalSignals

# Need two pivots plus RSI/MACD warm-up to read a divergence; below this → diagnostic.
_MIN_BARS = 35
_DOUBLE_TOL_PCT = 1.5  # two lows/highs within this % count as a "double" formation

_BULLISH = ("rsi_bullish_divergence", "macd_bullish_divergence", "double_bottom")
_BEARISH = ("rsi_bearish_divergence", "macd_bearish_divergence", "double_top")


def _indexed_pivots(
    bars: list[OHLCVBar], *, left: int, right: int
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Fractal swing pivots WITH their bar index → (highs, lows) as (idx, price)."""
    n = len(bars)
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(left, n - right):
        hi, lo = bars[i].high, bars[i].low
        if all(hi > bars[j].high for j in range(i - left, i)) and all(
            hi > bars[j].high for j in range(i + 1, i + right + 1)
        ):
            highs.append((i, hi))
        if all(lo < bars[j].low for j in range(i - left, i)) and all(
            lo < bars[j].low for j in range(i + 1, i + right + 1)
        ):
            lows.append((i, lo))
    return highs, lows


def _rsi_at(closes: list[float], i: int) -> float | None:
    return indicators.rsi(closes[: i + 1])


def _macd_hist_at(closes: list[float], i: int) -> float | None:
    m = indicators.macd(closes[: i + 1])
    return m[2] if m is not None else None


def detect(
    bars: list[OHLCVBar],
    *,
    left: int = 2,
    right: int = 2,
    double_tol_pct: float = _DOUBLE_TOL_PCT,
) -> TechnicalReversalSignals | None:
    """Detect reversal cues from closed bars, or None when there is too little data."""
    if len(bars) < _MIN_BARS:
        return None
    closes = [b.close for b in bars]
    highs, lows = _indexed_pivots(bars, left=left, right=right)
    signals: list[ReversalSignal] = []

    # ── divergence on the last two swing HIGHS → bearish ──────────────────────
    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        if p2 > p1:  # higher price high
            r1, r2 = _rsi_at(closes, i1), _rsi_at(closes, i2)
            if r1 is not None and r2 is not None and r2 < r1:
                signals.append(
                    ReversalSignal(
                        type="rsi_bearish_divergence",
                        detail=f"HH {p1:.4f}->{p2:.4f}, RSI {r1:.1f}->{r2:.1f}",
                    )
                )
            h1, h2 = _macd_hist_at(closes, i1), _macd_hist_at(closes, i2)
            if h1 is not None and h2 is not None and h2 < h1:
                signals.append(
                    ReversalSignal(
                        type="macd_bearish_divergence",
                        detail=f"HH price, MACD hist {h1:.5f}->{h2:.5f}",
                    )
                )

    # ── divergence on the last two swing LOWS → bullish ───────────────────────
    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p2 < p1:  # lower price low
            r1, r2 = _rsi_at(closes, i1), _rsi_at(closes, i2)
            if r1 is not None and r2 is not None and r2 > r1:
                signals.append(
                    ReversalSignal(
                        type="rsi_bullish_divergence",
                        detail=f"LL {p1:.4f}->{p2:.4f}, RSI {r1:.1f}->{r2:.1f}",
                    )
                )
            h1, h2 = _macd_hist_at(closes, i1), _macd_hist_at(closes, i2)
            if h1 is not None and h2 is not None and h2 > h1:
                signals.append(
                    ReversalSignal(
                        type="macd_bullish_divergence",
                        detail=f"LL price, MACD hist {h1:.5f}->{h2:.5f}",
                    )
                )

    # ── double bottom / top (two similar pivots with an opposite pivot between) ─
    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p1 > 0 and abs(p2 - p1) / p1 * 100.0 <= double_tol_pct and any(
            i1 < hi_i < i2 for hi_i, _ in highs
        ):
            signals.append(
                ReversalSignal(type="double_bottom", detail=f"lows {p1:.4f}≈{p2:.4f}")
            )
    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        if p1 > 0 and abs(p2 - p1) / p1 * 100.0 <= double_tol_pct and any(
            i1 < lo_i < i2 for lo_i, _ in lows
        ):
            signals.append(
                ReversalSignal(type="double_top", detail=f"highs {p1:.4f}≈{p2:.4f}")
            )

    bullish = sum(1 for s in signals if s.type in _BULLISH)
    bearish = sum(1 for s in signals if s.type in _BEARISH)
    bias = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
    return TechnicalReversalSignals(signals=signals, bias=bias)
