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
from packages.data.providers.technical import indicators
from packages.data.types import TIMEFRAMES, OHLCVBar, TechnicalSnapshot, Timeframe

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
        ts=bars[-1].ts if bars else now,
        status="DEGRADED" if degraded else "OK",
        source=bars[-1].source if bars else "none",
        bars_used=len(bars),
    )


def get_snapshot(symbol: str, timeframe: str = "1d") -> TechnicalSnapshot:
    tf: Timeframe = timeframe if timeframe in TIMEFRAMES else "1d"  # type: ignore[assignment]
    bars = ohlcv.get_bars(symbol, tf)
    return compute_snapshot(symbol, tf, bars)
