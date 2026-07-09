"""HTF (üst zaman dilimi) hiyerarşi — rejim-önce kapı (EVIDENCE only).

Owner sırası (2026-07-09): 1W/1D REJİM önce gelir, alt-TF setup ona UYMALI:
  - HH/HL (BULLISH) → yalnız LONG tarafı
  - LH/LL (BEARISH) → yalnız SHORT tarafı
  - RANGING → dipte long, tepede short, ORTADA işlem yok

200 EMA yalnız FİLTRE (bias'ı güçlendirir, tek başına işlem sebebi DEĞİL).

Saf fonksiyon; MarketStructure'lardan okur, uydurma yok (yetersiz → none).
Canlıya BAĞLI DEĞİL — yapısal skorlayıcı (touche revizyonu) tüketecek.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.signals.market_structure import MarketStructure

# Rejim kaynağı — öncelik sırası (en üst TF ilk).
HTF_ORDER = ("1w", "1W", "1d", "1D")


@dataclass(frozen=True)
class HtfBias:
    bias: str          # long | short | range | none
    source_tf: str | None
    trend: str | None  # BULLISH | BEARISH | RANGING
    reason: str


_TREND_BIAS = {"BULLISH": "long", "BEARISH": "short", "RANGING": "range"}


def htf_bias(structures: dict[str, MarketStructure | None]) -> HtfBias:
    """En üst mevcut TF'nin trendinden rejim bias'ı (1W > 1D)."""
    for tf in HTF_ORDER:
        ms = structures.get(tf)
        if ms is not None:
            bias = _TREND_BIAS.get(ms.trend, "none")
            return HtfBias(bias=bias, source_tf=tf, trend=ms.trend,
                           reason=f"{tf} {ms.trend} → {bias}")
    return HtfBias(bias="none", source_tf=None, trend=None, reason="HTF yapı yok")


def aligned(bias: str, direction: str, *, at_extreme: str | None = None) -> bool:
    """Alt-TF setup yönü HTF rejimiyle uyumlu mu (owner kuralı).

    - long/short bias → yalnız aynı yön.
    - range bias → long yalnız DİPTE (at_extreme='bottom'), short yalnız
      TEPEDE ('top'); ORTADA (None/'mid') işlem yok.
    """
    if direction not in ("long", "short"):
        return False
    if bias == "long":
        return direction == "long"
    if bias == "short":
        return direction == "short"
    if bias == "range":
        if direction == "long":
            return at_extreme == "bottom"
        return at_extreme == "top"
    return False


def ema_filter(price: float | None, ema200: float | None) -> str:
    """200 EMA filtresi: fiyat üstünde→long-dostu, altında→short-dostu, yoksa nötr.
    Owner: yalnız güçlendirici, tek başına işlem sebebi DEĞİL (skorda küçük katkı)."""
    if price is None or ema200 is None or ema200 <= 0:
        return "neutral"
    if price > ema200:
        return "long"
    if price < ema200:
        return "short"
    return "neutral"


def gate(
    structures: dict[str, MarketStructure | None],
    direction: str,
    *,
    at_extreme: str | None = None,
    price: float | None = None,
    ema200: float | None = None,
) -> dict:
    """Tam HTF kapısı: bias + hizalama + EMA filtresi tek çağrıda (yapısal
    skorlayıcının kullanacağı yüzey)."""
    hb = htf_bias(structures)
    ok = aligned(hb.bias, direction, at_extreme=at_extreme)
    ema = ema_filter(price, ema200)
    return {
        "bias": hb.bias,
        "source_tf": hb.source_tf,
        "aligned": ok,
        "ema_filter": ema,
        "ema_confirms": ema == direction,
        "reason": hb.reason,
    }


__all__ = ["HtfBias", "aligned", "ema_filter", "gate", "htf_bias"]
