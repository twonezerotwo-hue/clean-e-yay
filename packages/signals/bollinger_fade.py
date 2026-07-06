"""Bollinger Band-Fade sinyali — EVIDENCE only, salt-hesap.

Neden: `indicators.bollinger_width` yalnız GENİŞLİĞİ (volatilite rejimi) verir;
fiyatın banda göre KONUMU (band-touch mean-reversion) skorlanmıyor. Bu modül
onu ekler: fiyat üst banda değdi/aştı → geri çekilme (fade DOWN), alt banda →
sıçrama (fade UP). Trend TF'lerinde fiyat bandı sürebilir → orada TERS olması
beklenir (ölçüm gösterecek; vwap_fade deseni).

SAF fonksiyon: orta bant (SMA) + std kendi içinde (bollinger_width'in iç hesabı
ile eş, ~4 satır; ikisi de KULLANILIYOR → ölü değil). Band içinde → 0.0 (sinyal
yok). Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir.
"""
from __future__ import annotations


def lean(closes: list[float], *, period: int = 20, mult: float = 2.0) -> float | None:
    """Bollinger band-fade lean (−1..+1) veya None.

    Fiyat ≥ üst bant → −1 (fade down), ≤ alt bant → +1 (fade up), bant içi → 0.
    Yetersiz kapanış / dejenere bant → None.
    """
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((c - mean) ** 2 for c in window) / period
    std = var**0.5
    if std <= 0:
        return None  # dejenere (düz seri) — bant yok, uydurma yok
    band_pos = (closes[-1] - mean) / (mult * std)  # ±1 = banda tam değme
    if band_pos >= 1.0:
        return -1.0
    if band_pos <= -1.0:
        return 1.0
    return 0.0


__all__ = ["lean"]
