"""OBV eğilimi sinyali — EVIDENCE only, salt-hesap.

Hacim yönlü birikim/dağıtım: son `lookback` mumda yükselen kapanışların hacmi
eksi düşenlerin hacmi, toplam hacme oranlanır (−1..+1). Zayıf oran 0 sayılır.
Hacim yoksa None. Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir.
"""
from __future__ import annotations

from itertools import pairwise

_LOOKBACK = 20
_DEADBAND = 0.1
_FULL = 0.5


def lean(bars: list, *, lookback: int = _LOOKBACK) -> float | None:
    """Birikim (+) / dağıtım (−) oranı; |oran| < 0,1 → 0, hacim yoksa None."""
    if len(bars) < lookback + 1:
        return None
    window = bars[-lookback - 1:]
    signed = 0.0
    total = 0.0
    for prev, cur in pairwise(window):
        volume = getattr(cur, "volume", None)
        if volume is None:
            return None
        total += volume
        if cur.close > prev.close:
            signed += volume
        elif cur.close < prev.close:
            signed -= volume
    if total <= 0:
        return None
    ratio = signed / total
    if abs(ratio) < _DEADBAND:
        return 0.0
    return max(-1.0, min(1.0, ratio / _FULL))
