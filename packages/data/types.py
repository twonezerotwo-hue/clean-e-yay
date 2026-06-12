"""Veri katmanı için ortak veri tipleri (Pydantic)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


Direction = Literal["bullish", "bearish", "neutral"]
Sentiment = Direction
RegimeLabel = Literal["OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"]
AssetStatus = Literal["BLOCKING", "PENDING", "CONFIRMED"]

# T0 — Timeframe = first-class dimension. Sinyal uzayı (symbol, timeframe)
# çiftiyle anahtarlanır; risk/halt portföy seviyesinde global kalır.
Timeframe = Literal["15m", "1h", "4h", "1d", "1w"]
TIMEFRAMES: tuple[Timeframe, ...] = ("15m", "1h", "4h", "1d", "1w")
DEFAULT_TIMEFRAME: Timeframe = "1d"


PriceStatus = Literal["OK", "DATA_UNAVAILABLE", "MOCK"]


class PriceQuote(BaseModel):
    """Tek fiyat noktası.

    `price=None` → veri yok (runtime'da live provider başarısız). Mock
    verisi yalnızca test/dev modunda `status="MOCK"` ile döner;
    runtime'da kullanılmaz.
    """

    symbol: str
    price: float | None = None
    ts: datetime = Field(default_factory=utcnow)
    source: str = "unknown"
    verified: bool = False
    status: PriceStatus = "DATA_UNAVAILABLE"
    error: str | None = None
    fallback: bool = False  # geriye dönük uyumluluk için


class OHLCVBar(BaseModel):
    """Tek mum (T1). `ts` = bar açılış zamanı (UTC).

    `source` resample edilen barlarda `"resampled:<base_tf>"` taşır;
    fixture barları `source="fixture"`, `verified=False` damgalıdır ve
    runtime'da asla üretilmez (DATA_POLICY).
    """

    symbol: str
    timeframe: Timeframe
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str = "unknown"
    verified: bool = False


TechnicalStatus = Literal["OK", "DEGRADED"]


class TechnicalSnapshot(BaseModel):
    symbol: str
    timeframe: Timeframe = "1d"
    rsi: float | None = None
    # T1: macd = MACD(12/26/9) histogramının fiyata normalize edilmiş hali
    # ((macd_line - signal) / close * 100) — semboller arası karşılaştırılabilir.
    macd: float | None = None
    atr: float | None = None
    ema_stack: Literal["bullish", "bearish", "mixed"] | None = None
    score: float = 0.0
    ts: datetime = Field(default_factory=utcnow)
    # T1 additive — bar yetersiz/stale ise DEGRADED; alanlar None kalır.
    status: TechnicalStatus = "OK"
    source: str = "unknown"
    bars_used: int = 0


class NewsHeadline(BaseModel):
    id: str
    source: str
    region: str | None = None
    ts: datetime
    title: str
    title_tr: str | None = None
    sentiment: Sentiment | None = None
    asset_impact: dict[str, float] = Field(default_factory=dict)


class Catalyst(BaseModel):
    id: str
    ts: datetime
    title: str
    importance: Literal["low", "medium", "high"] = "low"
    region: str | None = None


class CatalystImpact(BaseModel):
    """T0 contract seed — half-life motoru v2.7 deep data ile gelir.

    Bu model şimdilik yalnızca sözleşmedir: hiçbir engine üretmez/tüketmez.
    Haber tipine göre asset × timeframe etki haritası taşır.
    """

    catalyst_id: str
    event_type: str                 # ceasefire | cpi | fomc | opec | etf_flow | ...
    surprise_level: float = 0.0     # -1..+1 (beklentiden sapma)
    affected_assets: list[str] = Field(default_factory=list)
    expected_half_life_minutes: int = 60
    affected_timeframes: list[Timeframe] = Field(default_factory=list)
    timeframe_bias: dict[Timeframe, Direction] = Field(default_factory=dict)
    valid_until: datetime | None = None
    decay_curve: Literal["exponential", "linear", "step"] = "exponential"
    confidence: float = 0.0         # 0..1 (kaynak doğrulaması)


class RotationView(BaseModel):
    name: str = "Sermaye Rotasyonu"
    score: float = 50.0
    direction: Direction = "neutral"
    evidence: list[str] = Field(default_factory=list)
