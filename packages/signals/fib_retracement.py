"""Fibonacci geri çekilme sinyali — EVIDENCE only, salt-hesap.

Son `lookback` mumdaki salınımın %61,8–%78,6 geri çekilme bölgesindeyse fiyat,
salınım yönünde devam beklenir: yükseliş salınımında (dip önce, tepe sonra)
bölgeye inen fiyat +1, düşüş salınımında bölgeye çıkan fiyat −1, aksi 0.
Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir; Soul'daki çizim aracının
kanıtı buradan gelir.
"""
from __future__ import annotations

_LOOKBACK = 60
_ZONE = (0.618, 0.786)


def lean(bars: list, *, lookback: int = _LOOKBACK) -> float | None:
    """Bölgedeyse salınım yönünde +1/−1, değilse 0; yetersiz veri None."""
    if len(bars) < lookback:
        return None
    window = bars[-lookback:]
    hi_i = max(range(len(window)), key=lambda i: window[i].high)
    lo_i = min(range(len(window)), key=lambda i: window[i].low)
    high, low = window[hi_i].high, window[lo_i].low
    span = high - low
    if span <= 0:
        return None
    close = window[-1].close
    if lo_i < hi_i:  # yükseliş salınımı
        depth = (high - close) / span
        return 1.0 if _ZONE[0] <= depth <= _ZONE[1] else 0.0
    depth = (close - low) / span  # düşüş salınımı
    return -1.0 if _ZONE[0] <= depth <= _ZONE[1] else 0.0
