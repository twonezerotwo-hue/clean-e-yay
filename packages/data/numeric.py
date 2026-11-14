"""Sayı olmayan değerlere karşı ortak koruma.

``max(lo, min(hi, x))`` kalıbı NaN'ı sessizce ``hi``'ye çevirir (NaN ile her
karşılaştırma yanlıştır): bozuk bir çarpan en büyük boyuta, bozuk bir skor 100'e
dönüşür. Karar zincirinde sıkıştırma bu yardımcılarla yapılır; sayı olmayan
girdi çağıranın seçtiği güvenli değere düşer.
"""
from __future__ import annotations

import math


def is_finite(x: object) -> bool:
    """Gerçek, sonlu bir sayı mı? (bool, None, NaN, ±inf → False)"""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def bounded(x: object, lo: float, hi: float, *, default: float) -> float:
    """``x``'i [lo, hi] aralığına sıkıştır; sayı değilse ``default``."""
    if not is_finite(x):
        return default
    return max(lo, min(hi, float(x)))  # type: ignore[arg-type]


__all__ = ["bounded", "is_finite"]
