"""Regime Gate sinyali — piyasa havası: 60-bar yön + Kaufman verimlilik (EVIDENCE only).

Neden (backtest kanıtı, 2026-07-06 derin kıyas): tek tarifle her havada uçulmuyor.
494 bindirmesiz pencerede — YÜKSELİŞ günlerinde 1d trend kral (+0.65%), DÜŞÜŞ
günlerinde trend kaybediyor (−0.19%) ve 4h yapı tek pozitif. Rejim-anahtarlı
kompozit (UP→trend, DOWN→yapı) taban +0.29'a karşı +0.53%/%59 isabet üretti
(iki-yarı kararlı, 6/9 sembol pozitif). Bu modül o anahtarın "hava ölçer"i.

İki okuma verir:
  - regime: "UP" | "DOWN" — son LOOKBACK barın net yönü (eşitlik → UP).
  - er: 0..1 Kaufman verimlilik oranı — |net hareket| / kat edilen yol.
    Yüksek = temiz trend, düşük = testere. (Backtest: ER≥0.30 filtresi UP'ta
    kenarı büyütür ama kapsamayı kısar — R1'de yalnız RAPORLANIR, kapı değil.)

`lean()` = ±1 (UP/DOWN) → karne (subsignal_scorecard) bunu diğer sinyallerle
AYNI sert cetvelden geçirir; yani "hava ölçer"in kendisi de kanıt üretmek
zorunda. SAF fonksiyon: look-ahead yok, yan etki yok, canlı karara bağlı değil.
"""
from __future__ import annotations

from dataclasses import dataclass

# Backtest'te seçilen pencereler (v2_deep_compare / v2_regime_composites):
# 60 bar trailing yön (1d'de ~3 ay), 20 bar verimlilik. Sabitler bilinçli —
# öğrenme/autotune kapsamı DEĞİL; değişiklik yeni ölçüm gerektirir.
LOOKBACK = 60
ER_PERIOD = 20


@dataclass(frozen=True)
class RegimeGate:
    regime: str   # UP | DOWN (son LOOKBACK barın net yönü; eşitlik → UP)
    er: float     # 0..1 Kaufman verimlilik (yüksek = temiz trend)
    lean: float   # +1 (UP) | −1 (DOWN) — karne ölçümü için yön okuması


def assess(closes: list[float]) -> RegimeGate | None:
    """Kapanışlardan hava okuması. Yetersiz veri → None (uydurma yok)."""
    if len(closes) < LOOKBACK + 1:
        return None
    last = closes[-1]
    ref = closes[-1 - LOOKBACK]
    regime = "UP" if last >= ref else "DOWN"

    net = abs(last - closes[-1 - ER_PERIOD])
    path = sum(
        abs(closes[i] - closes[i - 1])
        for i in range(len(closes) - ER_PERIOD, len(closes))
    )
    er = (net / path) if path > 0 else 0.0
    return RegimeGate(
        regime=regime,
        er=round(min(1.0, max(0.0, er)), 4),
        lean=1.0 if regime == "UP" else -1.0,
    )


def lean(closes: list[float]) -> float | None:
    """Ölçüm/skorlama için ince sarmalayıcı: ±1 veya None."""
    rg = assess(closes)
    return rg.lean if rg is not None else None


__all__ = ["ER_PERIOD", "LOOKBACK", "RegimeGate", "assess", "lean"]
