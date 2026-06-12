"""Saf indikatör fonksiyonları — gerçek OHLCV barlarından (T1).

Hepsi yetersiz veri durumunda None döner; asla uydurma değer üretmez
(DATA_POLICY). Wilder smoothing (RSI/ATR), klasik EMA seed = SMA.
"""
from __future__ import annotations

from itertools import pairwise

from packages.data.types import OHLCVBar


def ema_series(values: list[float], period: int) -> list[float] | None:
    """EMA serisi; ilk eleman ilk `period` değerin SMA'sıdır.
    Dönen liste `values[period-1:]` ile hizalıdır."""
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder RSI. En az period+1 kapanış gerekir."""
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, cur in pairwise(closes):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, lo in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + lo) / period
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float, float, float] | None:
    """(macd_line, signal_line, histogram). En az slow+signal-1 kapanış."""
    if len(closes) < slow + signal - 1:
        return None
    fast_s = ema_series(closes, fast)
    slow_s = ema_series(closes, slow)
    if not fast_s or not slow_s:
        return None
    # slow_s, closes[slow-1:] ile hizalı; fast_s'in son len(slow_s) elemanı eş.
    macd_line = [f - s for f, s in zip(fast_s[-len(slow_s):], slow_s, strict=True)]
    signal_s = ema_series(macd_line, signal)
    if not signal_s:
        return None
    return (macd_line[-1], signal_s[-1], macd_line[-1] - signal_s[-1])


def atr(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """Wilder ATR. En az period+1 bar gerekir."""
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for prev, cur in pairwise(bars):
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(tr)
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value
