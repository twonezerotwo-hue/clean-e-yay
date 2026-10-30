"""Hacim itkisi sinyali — EVIDENCE only, salt-hesap.

Neden (hedef mimari 3. aşama): teknik teyitte ayrı bir hacim ölçüsü yok.
Ortalamanın en az 1,5 katı hacimle kapanan mum, hareketin arkasında katılım
olduğunu gösterir; yön son kapanışın değişim yönüdür. Hacim yoksa (döviz,
endeks) None. Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir.
"""
from __future__ import annotations

_LOOKBACK = 20
_THRESHOLD = 1.5


def lean(bars: list, *, lookback: int = _LOOKBACK, threshold: float = _THRESHOLD) -> float | None:
    """Yüksek hacimli mumda yön (+1/−1), normal hacimde 0, hacim yoksa None."""
    if len(bars) < lookback + 2:
        return None
    volumes = [getattr(b, "volume", None) for b in bars[-lookback - 1:-1]]
    last = bars[-1]
    if any(v is None for v in volumes) or not getattr(last, "volume", None):
        return None
    average = sum(volumes) / len(volumes)
    if average <= 0:
        return None
    if last.volume < threshold * average:
        return 0.0
    move = last.close - bars[-2].close
    return 1.0 if move > 0 else -1.0 if move < 0 else 0.0
