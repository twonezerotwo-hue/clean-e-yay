"""RSI-Uç (extreme / fade) sinyali — EVIDENCE only, salt-hesap.

Neden: touche RSI'ı HER TF'de LİNEER yön-lean olarak kullanıyor (`(rsi−50)/50`)
— yani "RSI yüksek = al" (trend-takip). Faz A ölçtü: bu 15m/1h'de gürültü.
Ama kısa TF'de klasik edge TERS yöndedir: aşırı-alım (RSI≥70) → geri çekilme
(fade DOWN), aşırı-satım (RSI≤30) → sıçrama (fade UP). Bu modül o **fade**
okumasını ayrı bir sinyal olarak verir; touche'un lineer lean'inin TERSİ
polaritede (yalnız uçlarda konuşur, ortada susar).

SAF fonksiyon: `indicators.rsi` (kopya yok). Uç dışında lean 0 (sinyal yok,
uydurma yok). Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators

# Uç eşikleri (klasik 70/30). Config'e taşınabilir; şimdilik sabit + ölçülür.
_OVERBOUGHT = 70.0
_OVERSOLD = 30.0


def lean(
    closes: list[float], *, period: int = 14,
    overbought: float = _OVERBOUGHT, oversold: float = _OVERSOLD,
) -> float | None:
    """RSI-uç fade lean (−1..+1) veya None.

    RSI≥overbought → NEGATİF (fade down, geri çekilme beklentisi), uçtan uzaklaştıkça büyür.
    RSI≤oversold  → POZİTİF (fade up, sıçrama beklentisi).
    Ortada (oversold<RSI<overbought) → 0.0 (sinyal yok — uçta olmayan RSI fade üretmez).
    """
    rsi_v = indicators.rsi(closes, period=period)
    if rsi_v is None:
        return None
    if rsi_v >= overbought:
        span = max(1e-9, 100.0 - overbought)
        return -min(1.0, (rsi_v - overbought) / span)
    if rsi_v <= oversold:
        span = max(1e-9, oversold)
        return min(1.0, (oversold - rsi_v) / span)
    return 0.0


__all__ = ["lean"]
