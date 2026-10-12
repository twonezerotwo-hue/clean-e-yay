"""Market Structure sinyali — HH/HL/LH/LL dizisi + BOS + CHoCH (EVIDENCE only).

Neden: mevcut `patterns.py` yalnız SON 2 pivotu kaba okur ve zayıf bir tilt
kanadıdır. Piyasa yapısı fiyatı DOĞRUDAN okur (gecikmesiz) → her TF'de anlamlı.

v2 — DERİNLEŞTİRİLMİŞ:
  - Tam kronolojik swing dizisi: tepe/dip pivotları zamanda birleştirilip
    ardışık aynı-tür pivotlar temizlenir (gerçek zigzag) → doğru "en son swing".
  - BOS (Break of Structure): trend yönünde en son swing'i kırış → devam teyidi.
  - CHoCH (Change of Character): trend karşıtı en son swing'i kırış → dönüş İLK
    işareti (en güçlü sinyal).
  - Trend OLGUNLUĞU: ardışık HH/HL (veya LH/LL) sayısı → uzun seri = tükenme
    riski → devam/trend lean'i sönümlenir (körlemesine kovalamayı azaltır).

SAF fonksiyon: kendi fraktal pivot helper'ı (indicators.swing_pivots ile aynı
kural; indeks gerektiği için burada — reversal'ın private kopyasıyla eş, ama her
ikisi de KULLANILIYOR, ölü değil). Look-ahead yok. Canlı skora BAĞLI DEĞİL —
ölçüm (scorecard) tüketir.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.types import OHLCVBar

_MIN_BARS = 20


@dataclass(frozen=True)
class MarketStructure:
    trend: str          # BULLISH | BEARISH | RANGING (swing dizisinden)
    lean: float         # −1..+1 yön okuması (CHoCH>BOS>trend, olgunlukla sönümlü)
    bos: str            # none | bullish | bearish (yapı kırılımı = devam)
    choch: str          # none | bullish | bearish (karakter değişimi = dönüş)
    streak: int         # ardışık aynı-yön swing sayısı (trend olgunluğu)
    legs: int           # temizlenmiş zigzag'daki swing sayısı
    detail: str


def _pivots(bars: list[OHLCVBar], left: int, right: int) -> list[tuple[int, float, str]]:
    """Fraktal swing pivotları → kronolojik (index, price, 'H'|'L'). indicators.
    swing_pivots ile AYNI kural + indeks (dizi kurmak için gerekli)."""
    n = len(bars)
    piv: list[tuple[int, float, str]] = []
    for i in range(left, n - right):
        hi, lo = bars[i].high, bars[i].low
        if all(hi > bars[j].high for j in range(i - left, i)) and all(
            hi > bars[j].high for j in range(i + 1, i + right + 1)
        ):
            piv.append((i, hi, "H"))
        if all(lo < bars[j].low for j in range(i - left, i)) and all(
            lo < bars[j].low for j in range(i + 1, i + right + 1)
        ):
            piv.append((i, lo, "L"))
    piv.sort(key=lambda x: x[0])
    return piv


def _zigzag(piv: list[tuple[int, float, str]]) -> list[tuple[int, float, str]]:
    """Ardışık aynı-tür pivotları temizle: iki tepe arası dip yoksa daha yüksek
    tepeyi tut (iki dip arası tepe yoksa daha düşük dibi tut) → gerçek zigzag."""
    seq: list[tuple[int, float, str]] = []
    for p in piv:
        if seq and seq[-1][2] == p[2]:
            keep_new = (p[1] > seq[-1][1]) if p[2] == "H" else (p[1] < seq[-1][1])
            if keep_new:
                seq[-1] = p
        else:
            seq.append(p)
    return seq


def _streak(highs: list[float], lows: list[float], bullish: bool) -> int:
    """Sondan ardışık HH+HL (bullish) / LH+LL (bearish) sayısı."""
    s = 0
    hi = len(highs) - 1
    lo = len(lows) - 1
    while hi >= 1 and lo >= 1:
        hh = highs[hi] > highs[hi - 1]
        hl = lows[lo] > lows[lo - 1]
        ok = (hh and hl) if bullish else ((not hh) and (not hl))
        if not ok:
            break
        s += 1
        hi -= 1
        lo -= 1
    return s


def analyze(bars: list[OHLCVBar], *, left: int = 2, right: int = 2) -> MarketStructure | None:
    """Bars'tan derinleştirilmiş yapı okuması. Yetersiz veri → None (uydurma yok)."""
    if len(bars) < _MIN_BARS:
        return None
    seq = _zigzag(_pivots(bars, left, right))
    highs = [p[1] for p in seq if p[2] == "H"]
    lows = [p[1] for p in seq if p[2] == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None

    hh = highs[-1] > highs[-2]
    hl = lows[-1] > lows[-2]
    lh = highs[-1] < highs[-2]
    ll = lows[-1] < lows[-2]
    if hh and hl:
        trend = "BULLISH"
    elif lh and ll:
        trend = "BEARISH"
    else:
        trend = "RANGING"

    streak = _streak(highs, lows, bullish=(trend == "BULLISH")) if trend != "RANGING" else 0
    price = bars[-1].close
    last_high = highs[-1]
    last_low = lows[-1]
    bos = "none"
    choch = "none"
    if trend == "BULLISH":
        if price > last_high:
            bos = "bullish"
        if price < last_low:
            choch = "bearish"
    elif trend == "BEARISH":
        if price < last_low:
            bos = "bearish"
        if price > last_high:
            choch = "bullish"
    else:
        if price > last_high:
            choch = "bullish"
        elif price < last_low:
            choch = "bearish"

    # Olgunluk sönümü: uzun seri (≥3 ardışık) devam sinyalini zayıflatır
    # (tükenme riski). CHoCH dönüş sinyali olduğu için sönümlenmez.
    damp = 1.0 if streak < 3 else max(0.5, 1.0 - 0.15 * (streak - 2))
    if choch == "bullish":
        lean = 1.0
    elif choch == "bearish":
        lean = -1.0
    elif bos == "bullish":
        lean = 0.7 * damp
    elif bos == "bearish":
        lean = -0.7 * damp
    elif trend == "BULLISH":
        lean = 0.4 * damp
    elif trend == "BEARISH":
        lean = -0.4 * damp
    else:
        lean = 0.0

    detail = (
        f"{trend} bos={bos} choch={choch} streak={streak} legs={len(seq)} "
        f"H[{last_high:.6g}] L[{last_low:.6g}] px[{price:.6g}]"
    )
    return MarketStructure(
        trend=trend, lean=round(lean, 4), bos=bos, choch=choch,
        streak=streak, legs=len(seq), detail=detail,
    )


def lean(bars: list[OHLCVBar], *, left: int = 2, right: int = 2) -> float | None:
    """Ölçüm/skorlama için ince sarmalayıcı: yön okuması (−1..+1) veya None."""
    ms = analyze(bars, left=left, right=right)
    return ms.lean if ms is not None else None


@dataclass(frozen=True)
class StructureBreak:
    """Tek bir yapı kırılımının OLAY hâli (``analyze`` yalnız anlık durumu verir).

    ``bar_index``: kırılımın SİSTEM TARAFINDAN bilindiği bar = max(ilk kapanış-ötesi
    bar, referans pivotun teyit barı). Pivot teyidi ``right`` bar gecikmelidir; bu
    yüzden olay hiçbir zaman henüz bilinemeyecek bir pivota dayanmaz (look-ahead yok).
    """

    kind: str            # choch | bos
    direction: str       # bullish | bearish (kırılımın yönü)
    bar_index: int       # olayın bilindiği bar
    level: float         # kırılan swing seviyesi
    margin: float        # kırılış barı kapanışının seviyeyi aşma mesafesi (fiyat)
    prior_streak: int    # kırılımdan önceki trendin ardışık HH/HL (LH/LL) serisi
    still_beyond: bool   # son kapanış hâlâ kırılan seviyenin ötesinde mi


def swing_levels(
    bars: list[OHLCVBar], *, left: int = 2, right: int = 2
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Temizlenmiş zigzag'daki TEYİTLİ (index, fiyat) tepeleri ve dipleri.
    ``analyze`` ile aynı pivot/zigzag kuralı — tek tanım."""
    seq = _zigzag(_pivots(bars, left, right))
    return (
        [(i, p) for i, p, k in seq if k == "H"],
        [(i, p) for i, p, k in seq if k == "L"],
    )


def _first_close_beyond(bars: list[OHLCVBar], start: int, level: float, above: bool) -> int | None:
    for j in range(start + 1, len(bars)):
        c = bars[j].close
        if (c > level) if above else (c < level):
            return j
    return None


def break_events(
    bars: list[OHLCVBar], *, left: int = 2, right: int = 2
) -> list[StructureBreak]:
    """CHoCH / BOS OLAYLARI (en son referans swing'e göre) — yaş hesaplanabilsin diye.

    ``analyze`` ile aynı trend tanımı: BULLISH (HH+HL) → tepe üstü kapanış = BOS,
    dip altı kapanış = CHoCH; BEARISH (LH+LL) → ayna; RANGING → iki yönde de CHoCH.
    Fark: ``analyze`` yalnız SON kapanışın durumuna bakar; burada kırılışın ilk
    kapanış barı bulunur (kırılım sonradan geri alınmış olsa da olay kayıtlıdır,
    ``still_beyond`` bunu söyler). Yetersiz veri → boş liste."""
    if len(bars) < _MIN_BARS:
        return []
    hs, ls = swing_levels(bars, left=left, right=right)
    if len(hs) < 2 or len(ls) < 2:
        return []
    highs = [p for _, p in hs]
    lows = [p for _, p in ls]
    hh, hl = highs[-1] > highs[-2], lows[-1] > lows[-2]
    lh, ll = highs[-1] < highs[-2], lows[-1] < lows[-2]
    trend = "BULLISH" if (hh and hl) else ("BEARISH" if (lh and ll) else "RANGING")
    streak = _streak(highs, lows, bullish=(trend == "BULLISH")) if trend != "RANGING" else 0
    price = bars[-1].close
    (hi_idx, hi_lvl), (lo_idx, lo_lvl) = hs[-1], ls[-1]

    out: list[StructureBreak] = []

    def _add(kind: str, direction: str, ref_idx: int, level: float, above: bool) -> None:
        j = _first_close_beyond(bars, ref_idx, level, above)
        if j is None:
            return
        known = max(j, ref_idx + right)
        margin = abs(bars[j].close - level)
        beyond = (price > level) if above else (price < level)
        out.append(StructureBreak(kind, direction, known, level, margin, streak, beyond))

    if trend == "BULLISH":
        _add("bos", "bullish", hi_idx, hi_lvl, True)
        _add("choch", "bearish", lo_idx, lo_lvl, False)
    elif trend == "BEARISH":
        _add("bos", "bearish", lo_idx, lo_lvl, False)
        _add("choch", "bullish", hi_idx, hi_lvl, True)
    else:
        _add("choch", "bullish", hi_idx, hi_lvl, True)
        _add("choch", "bearish", lo_idx, lo_lvl, False)
    return out


__all__ = [
    "MarketStructure",
    "StructureBreak",
    "analyze",
    "break_events",
    "lean",
    "swing_levels",
]
