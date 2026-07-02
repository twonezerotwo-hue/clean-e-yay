"""T-4 — Mum teyidi: pin bar + engulfing tespiti (EVIDENCE only).

`patterns.py`/`reversal.py` ile aynı desen: yalnız KAPANMIŞ barlar üzerinde
pure fonksiyon, veri yetersizse None (uydurma sinyal yok). Tek başına asla
yön üretmez — `_pattern_alignment` içinde momentumla uyum/çelişki tartılır
ve YALNIZ fiyat bir confluence bölgesindeyken sayılır (genel mum taraması
gürültüdür; kilit seviyedeki dönüş mumu kanıttır).

Öncelik: engulfing (iki-bar, daha güçlü yapı) > pin bar (tek-bar rejeksiyon).
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.types import OHLCVBar

_MIN_BARS = 3
# Pin bar: rejeksiyon fitili gövdenin en az bu katı olmalı; karşı fitil
# gövdeyi aşmamalı (aksi halde kararsız/spinning-top, rejeksiyon değil).
_PIN_WICK_BODY_RATIO = 2.0


@dataclass(frozen=True)
class CandleSignal:
    name: str      # bullish_engulfing / bearish_engulfing / hammer / shooting_star
    bias: str      # BULLISH / BEARISH
    detail: str


def _engulfing(prev: OHLCVBar, last: OHLCVBar) -> CandleSignal | None:
    prev_body_hi = max(prev.open, prev.close)
    prev_body_lo = min(prev.open, prev.close)
    if prev_body_hi <= prev_body_lo:  # önceki bar gövdesiz (doji) — yutulacak şey yok
        return None
    # Boğa: kırmızı gövdeyi tamamen yutan yeşil gövde.
    if (
        last.close > last.open
        and prev.close < prev.open
        and last.open <= prev_body_lo
        and last.close >= prev_body_hi
    ):
        return CandleSignal(
            name="bullish_engulfing",
            bias="BULLISH",
            detail=f"green body [{last.open:.6g},{last.close:.6g}] engulfs red [{prev_body_lo:.6g},{prev_body_hi:.6g}]",
        )
    # Ayı: yeşil gövdeyi tamamen yutan kırmızı gövde.
    if (
        last.close < last.open
        and prev.close > prev.open
        and last.open >= prev_body_hi
        and last.close <= prev_body_lo
    ):
        return CandleSignal(
            name="bearish_engulfing",
            bias="BEARISH",
            detail=f"red body [{last.close:.6g},{last.open:.6g}] engulfs green [{prev_body_lo:.6g},{prev_body_hi:.6g}]",
        )
    return None


def _pin_bar(last: OHLCVBar) -> CandleSignal | None:
    rng = last.high - last.low
    body = abs(last.close - last.open)
    if rng <= 0 or body <= 0:  # gövdesiz/aralıksız bar — rejeksiyon okunamaz
        return None
    upper = last.high - max(last.close, last.open)
    lower = min(last.close, last.open) - last.low
    mid = (last.high + last.low) / 2.0
    # Hammer: uzun alt fitil (satıcı reddedildi) + kapanış üst yarıda.
    if lower >= _PIN_WICK_BODY_RATIO * body and upper <= body and last.close > mid:
        return CandleSignal(
            name="hammer",
            bias="BULLISH",
            detail=f"lower wick {lower:.6g} >= {_PIN_WICK_BODY_RATIO}x body {body:.6g}",
        )
    # Shooting star: uzun üst fitil (alıcı reddedildi) + kapanış alt yarıda.
    if upper >= _PIN_WICK_BODY_RATIO * body and lower <= body and last.close < mid:
        return CandleSignal(
            name="shooting_star",
            bias="BEARISH",
            detail=f"upper wick {upper:.6g} >= {_PIN_WICK_BODY_RATIO}x body {body:.6g}",
        )
    return None


def detect(bars: list[OHLCVBar]) -> CandleSignal | None:
    """Son kapanmış bardaki dönüş mumu — yoksa None (asla uydurulmaz)."""
    if len(bars) < _MIN_BARS:
        return None
    prev, last = bars[-2], bars[-1]
    return _engulfing(prev, last) or _pin_bar(last)


__all__ = ["CandleSignal", "detect"]
