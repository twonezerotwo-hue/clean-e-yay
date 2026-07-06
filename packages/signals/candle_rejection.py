"""Candle-Rejection sinyali — EVIDENCE only, salt-hesap.

Neden: `candles.detect` (engulfing/pin/hammer/shooting_star) CANLI skorda
`candle_confirm` flag'i KAPALI olduğu için kullanılmıyor. Bu modül o dedektörü
REUSE edip yön sinyaline çevirir: rejeksiyon mumu = giriş zamanlaması. Bullish
rejeksiyon (bullish_engulfing/hammer) → +, bearish (bearish_engulfing/
shooting_star) → −. Engulfing (iki-bar, daha güçlü yapı) > pin bar (tek-bar).

SAF: `candles.detect` (kopya yok, kapalı dedektörü ölçüme bağlar). Mum sinyali
yoksa → None (o barda sinyal yok). Canlı skora BAĞLI DEĞİL — scorecard tüketir.
"""
from __future__ import annotations

from packages.data.providers.technical import candles
from packages.data.types import OHLCVBar


def lean(bars: list[OHLCVBar]) -> float | None:
    """Candle-rejection lean (−1..+1) veya None (mum sinyali yoksa).

    Engulfing → ±1.0 (iki-bar güçlü rejeksiyon); pin/hammer/shooting_star →
    ±0.7 (tek-bar). Yön mumun bias'ından (BULLISH +, BEARISH −).
    """
    sig = candles.detect(bars)
    if sig is None:
        return None
    mag = 1.0 if "engulfing" in sig.name else 0.7
    return mag if sig.bias == "BULLISH" else -mag


__all__ = ["lean"]
