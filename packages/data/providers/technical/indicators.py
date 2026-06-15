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


def atr_percent(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """ATR'nin son kapanışa oranı (%) — semboller arası karşılaştırılabilir
    volatilite ölçüsü. ATR yoksa veya fiyat geçersizse None."""
    a = atr(bars, period)
    if a is None or not bars or bars[-1].close <= 0:
        return None
    return a / bars[-1].close * 100.0


def adx(bars: list[OHLCVBar], period: int = 14) -> tuple[float, float, float] | None:
    """Wilder ADX + yön göstergeleri → (adx, +DI, -DI).

    Trend gücü ölçer (yön değil): ADX yüksek = güçlü trend, düşük = range.
    Kararlı ADX için en az 2*period+1 bar gerekir; altı → None (DATA_POLICY).
    """
    if len(bars) < 2 * period + 1:
        return None
    trs: list[float] = []
    plus_dms: list[float] = []
    minus_dms: list[float] = []
    for prev, cur in pairwise(bars):
        up_move = cur.high - prev.high
        down_move = prev.low - cur.low
        plus_dms.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dms.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        trs.append(
            max(
                cur.high - cur.low,
                abs(cur.high - prev.close),
                abs(cur.low - prev.close),
            )
        )

    # Wilder smoothing (running sums) — ATR/RSI ile aynı teknik.
    atr_s = sum(trs[:period])
    plus_s = sum(plus_dms[:period])
    minus_s = sum(minus_dms[:period])

    def _di(plus_sum: float, minus_sum: float, atr_sum: float) -> tuple[float, float]:
        if atr_sum == 0.0:
            return 0.0, 0.0
        return 100.0 * plus_sum / atr_sum, 100.0 * minus_sum / atr_sum

    def _dx(plus_di: float, minus_di: float) -> float:
        denom = plus_di + minus_di
        return 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0

    plus_di, minus_di = _di(plus_s, minus_s, atr_s)
    dxs: list[float] = [_dx(plus_di, minus_di)]
    for i in range(period, len(trs)):
        atr_s = atr_s - atr_s / period + trs[i]
        plus_s = plus_s - plus_s / period + plus_dms[i]
        minus_s = minus_s - minus_s / period + minus_dms[i]
        plus_di, minus_di = _di(plus_s, minus_s, atr_s)
        dxs.append(_dx(plus_di, minus_di))

    if len(dxs) < period:
        return None
    adx_v = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        adx_v = (adx_v * (period - 1) + dx) / period
    # +DI / -DI son (en güncel) değerleriyle birlikte dön.
    return adx_v, plus_di, minus_di


def swing_pivots(
    bars: list[OHLCVBar], *, left: int = 2, right: int = 2
) -> tuple[list[float], list[float]] | None:
    """Fraktal swing pivotları → (swing_highs, swing_lows), kronolojik sırada.

    Bir bar, solundaki `left` ve sağındaki `right` barın hepsinden kesinkes
    yüksek (pivot high) / düşük (pivot low) ise pivottur. Yeterli bar yoksa
    None; pivot bulunmazsa boş listeler (uydurma seviye yok)."""
    n = len(bars)
    if n < left + right + 1:
        return None
    highs: list[float] = []
    lows: list[float] = []
    for i in range(left, n - right):
        hi = bars[i].high
        lo = bars[i].low
        is_high = all(hi > bars[j].high for j in range(i - left, i)) and all(
            hi > bars[j].high for j in range(i + 1, i + right + 1)
        )
        is_low = all(lo < bars[j].low for j in range(i - left, i)) and all(
            lo < bars[j].low for j in range(i + 1, i + right + 1)
        )
        if is_high:
            highs.append(hi)
        if is_low:
            lows.append(lo)
    return highs, lows


def vwap(bars: list[OHLCVBar]) -> float | None:
    """Hacim ağırlıklı ortalama fiyat (typical price = (H+L+C)/3).

    VWAP yalnızca intraday TF'lerde anlamlıdır (per-TF semantik kuralı çağıran
    tarafça uygulanır). Herhangi bir barda hacim yoksa/negatifse None —
    uydurma hacim yok (DATA_POLICY)."""
    if not bars:
        return None
    pv = 0.0
    vol = 0.0
    for b in bars:
        if b.volume is None or b.volume < 0:
            return None
        typical = (b.high + b.low + b.close) / 3.0
        pv += typical * b.volume
        vol += b.volume
    if vol <= 0:
        return None
    return pv / vol


def bollinger_width(closes: list[float], period: int = 20, mult: float = 2.0) -> float | None:
    """Bollinger bant genişliği = (üst-alt)/orta × 100 (% cinsinden).

    Volatilite rejimi (SQUEEZE/EXPANSION) için kullanılır. En az `period`
    kapanış gerekir; orta bant ≤ 0 ise None."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    if mean <= 0:
        return None
    var = sum((c - mean) ** 2 for c in window) / period
    std = var**0.5
    return (2.0 * mult * std) / mean * 100.0
