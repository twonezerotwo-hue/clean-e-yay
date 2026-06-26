"""Fractal pivot detection + alternating-sequence merge (P0..P5 girdisi).

Pure functions over closed OHLCV bars. Aynı fraktal pivot algoritmasını
`packages/data/providers/technical/indicators.py::swing_pivots` ve
`reversal.py::_indexed_pivots` zaten kullanıyor; bu modül onları
DEĞİŞTİRMEZ / yeniden uygulamaz — Elliott motoru için ayrı bir ihtiyacı
(bar-indeksli + KESİNTİSİZ ALTERNATİF high/low dizisi) karşılayan, kendi
başına test edilebilir bir yardımcıdır. Uydurma pivot yok: yetersiz bar
→ boş liste (DATA_POLICY).
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.types import OHLCVBar

PivotKind = str  # "high" | "low"


@dataclass(frozen=True)
class Pivot:
    bar_index: int
    price: float
    kind: PivotKind  # "high" | "low"
    ts: str | None = None


def _raw_pivots(bars: list[OHLCVBar], *, left: int, right: int) -> list[Pivot]:
    """Fraktal pivotlar, kronolojik sırada (aynı bar hem high hem low pivotu olabilir)."""
    n = len(bars)
    if n < left + right + 1:
        return []
    out: list[Pivot] = []
    for i in range(left, n - right):
        hi, lo = bars[i].high, bars[i].low
        ts = bars[i].ts.isoformat() if bars[i].ts else None
        if all(hi > bars[j].high for j in range(i - left, i)) and all(
            hi > bars[j].high for j in range(i + 1, i + right + 1)
        ):
            out.append(Pivot(bar_index=i, price=hi, kind="high", ts=ts))
        if all(lo < bars[j].low for j in range(i - left, i)) and all(
            lo < bars[j].low for j in range(i + 1, i + right + 1)
        ):
            out.append(Pivot(bar_index=i, price=lo, kind="low", ts=ts))
    out.sort(key=lambda p: p.bar_index)
    return out


def alternating_pivots(
    bars: list[OHLCVBar], *, left: int = 3, right: int = 3
) -> list[Pivot]:
    """Wave-sayımı için gereken KESİNTİSİZ high/low alternatif dizisi.

    Ardışık aynı-tür pivotlar (örn. iki ardışık 'high') birleştirilir —
    en ekstrem (en yüksek high / en düşük low) olan tutulur. Bu, Elliott
    dalga noktalarının (P0..P5) gerektirdiği "her dalga bir önceki yönün
    tersi" yapısını üretir; uydurma nokta eklenmez, sadece birleştirme yapılır.
    """
    raw = _raw_pivots(bars, left=left, right=right)
    if not raw:
        return []
    merged: list[Pivot] = [raw[0]]
    for p in raw[1:]:
        last = merged[-1]
        if p.kind == last.kind:
            keep = p if (p.kind == "high" and p.price > last.price) or (
                p.kind == "low" and p.price < last.price
            ) else last
            merged[-1] = keep
        else:
            merged.append(p)
    return merged


def last_n_alternating(
    bars: list[OHLCVBar], n: int, *, left: int = 3, right: int = 3
) -> list[Pivot]:
    """Sondan `n` alternatif pivot (wave sayımı için P0..P(n-1)); yetersizse []."""
    seq = alternating_pivots(bars, left=left, right=right)
    if len(seq) < n:
        return []
    return seq[-n:]


__all__ = ["Pivot", "alternating_pivots", "last_n_alternating"]
