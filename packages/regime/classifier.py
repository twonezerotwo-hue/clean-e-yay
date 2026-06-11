"""Makro rejim sınıflandırıcı.

Dört katman (likidite, enflasyon, risk iştahı, volatilite) → tek RegimeLabel.
Mock veriyle deterministik ama gerçekçi sonuçlar üretir.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.types import RegimeLabel


@dataclass
class RegimeLayer:
    name: str
    score: float            # 0–100
    direction: str          # bullish / bearish / neutral
    evidence: list[str]


@dataclass
class RegimeOutput:
    label: RegimeLabel
    layers: list[RegimeLayer]


def _direction(score: float) -> str:
    if score >= 55:
        return "bullish"
    if score <= 45:
        return "bearish"
    return "neutral"


def _price_or(snap: MarketSnapshot, symbol: str, default: float) -> float:
    for q in snap.prices:
        if q.symbol == symbol and q.price is not None:
            return q.price
    return default


def _liquidity_layer(snap: MarketSnapshot) -> RegimeLayer:
    dxy = _price_or(snap, "DXY", 104.0)
    us10y = _price_or(snap, "US10Y", 4.3)
    # Yüksek DXY + yüksek getiri → likidite daralıyor
    score = max(0.0, min(100.0, 100.0 - (dxy - 100.0) * 2.0 - (us10y - 4.0) * 5.0))
    return RegimeLayer(
        name="Likidite",
        score=round(score, 1),
        direction=_direction(score),
        evidence=[f"DXY {dxy:.2f}", f"US10Y {us10y:.2f}%"],
    )


def _appetite_layer(snap: MarketSnapshot) -> RegimeLayer:
    vix = _price_or(snap, "VIX", 14.0)
    # Düşük VIX → risk iştahı yüksek
    score = max(0.0, min(100.0, 100.0 - (vix - 12.0) * 4.0))
    return RegimeLayer(
        name="Risk İştahı",
        score=round(score, 1),
        direction=_direction(score),
        evidence=[f"VIX {vix:.1f}"],
    )


def _crypto_layer(snap: MarketSnapshot) -> RegimeLayer:
    btc_tech = snap.technicals.get("BTCUSD")
    base = btc_tech.score if btc_tech else 50.0
    return RegimeLayer(
        name="Kripto Momentum",
        score=round(base, 1),
        direction=_direction(base),
        evidence=[
            f"BTC RSI {btc_tech.rsi:.1f}" if btc_tech and btc_tech.rsi is not None else "—",
            f"BTC EMA {btc_tech.ema_stack}" if btc_tech else "—",
        ],
    )


def _rotation_layer(snap: MarketSnapshot) -> RegimeLayer:
    r = snap.rotation
    return RegimeLayer(
        name="Sermaye Rotasyonu",
        score=r.score,
        direction=r.direction,
        evidence=list(r.evidence),
    )


def classify(snap: MarketSnapshot) -> RegimeOutput:
    layers = [
        _liquidity_layer(snap),
        _appetite_layer(snap),
        _crypto_layer(snap),
        _rotation_layer(snap),
    ]
    avg = sum(layer.score for layer in layers) / len(layers)
    label: RegimeLabel
    if avg >= 65:
        label = "OFFENSIVE"
    elif avg >= 50:
        label = "NEUTRAL"
    elif avg >= 35:
        label = "DEFENSIVE"
    else:
        label = "CRISIS"
    return RegimeOutput(label=label, layers=layers)
