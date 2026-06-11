"""Veri katmanı için ortak veri tipleri (Pydantic)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Direction = Literal["bullish", "bearish", "neutral"]
Sentiment = Direction
RegimeLabel = Literal["OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"]
AssetStatus = Literal["BLOCKING", "PENDING", "CONFIRMED"]


class PriceQuote(BaseModel):
    symbol: str
    price: float
    ts: datetime = Field(default_factory=utcnow)
    source: str = "mock"
    fallback: bool = False


class TechnicalSnapshot(BaseModel):
    symbol: str
    timeframe: Literal["1h", "4h", "1d"] = "1d"
    rsi: float | None = None
    macd: float | None = None
    atr: float | None = None
    ema_stack: Literal["bullish", "bearish", "mixed"] | None = None
    score: float = 0.0
    ts: datetime = Field(default_factory=utcnow)


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


class RotationView(BaseModel):
    name: str = "Sermaye Rotasyonu"
    score: float = 50.0
    direction: Direction = "neutral"
    evidence: list[str] = Field(default_factory=list)
