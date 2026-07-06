"""VWAP-Sapma/Fade sinyali — EVIDENCE only, salt-hesap.

Neden: touche VWAP'ı yalnız basit "fiyat üstünde/altında" yön teyidi olarak
kullanıyor. Ama zengin `packages/vwap/engine.py` (deviation/reclaim/rejection)
CANLI KARARA BAĞLI DEĞİL (orphan). Bu modül o motoru YENİDEN KULLANIP kısa-TF
mean-reversion okumasını verir: fiyat VWAP'tan AŞIRI saptıysa VWAP'a geri
dönüş beklentisi (fade). Üstte aşırı → fade DOWN, altta aşırı → fade UP.

VWAP intraday kavramı → yalnız `INTRADAY_TF` (15m/1h/4h); 1d → None.
SAF: `vwap/engine.analyze` (kopya yok, orphan'ı ölçüme bağlar). Aşırı değilse
0.0 (sinyal yok). Canlı skora BAĞLI DEĞİL — ölçüm (scorecard) tüketir.
"""
from __future__ import annotations

from packages.data.providers.technical.timeframe import INTRADAY_TF
from packages.data.types import OHLCVBar
from packages.vwap import engine as vwap_engine


def lean(bars: list[OHLCVBar], *, timeframe: str) -> float | None:
    """VWAP-fade lean (−1..+1) veya None.

    Yalnız intraday TF'de + geçerli VWAP + AŞIRI sapmada konuşur:
      konum üstte & aşırı → −1 (VWAP'a geri fade DOWN)
      konum altta & aşırı → +1 (fade UP)
    Aşırı değil → 0.0 (sinyal yok). Intraday değil / VWAP yoksa → None.
    """
    if timeframe not in INTRADAY_TF:
        return None
    a = vwap_engine.analyze(bars, timeframe=timeframe)
    if a.validity in ("unavailable", "weak"):
        return None
    if not a.deviation_extreme:
        return 0.0
    if a.location == "above":
        return -1.0   # aşırı üstte → VWAP'a dönüş beklentisi (fade down)
    if a.location == "below":
        return 1.0    # aşırı altta → fade up
    return 0.0


__all__ = ["lean"]
