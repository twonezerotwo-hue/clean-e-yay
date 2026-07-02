"""Makro rejim sınıflandırıcı.

Dört katman (likidite, risk iştahı, kripto momentum, rotasyon) → tek
RegimeLabel. Katman girdileri gerçek snapshot fiyatlarından okunur.

F2-3 — `regime.drop_unavailable_layers` (owner-flag, default KAPALI):
KAPALI → eski davranış birebir: eksik makro veri sabit default'la doldurulur
(US10Y yoksa 4.3 varsayılır — "sessiz sahte skor"). AÇIK → veri olmayan
katman skor ÜRETMEZ, düşer (`RegimeOutput.dropped`); ortalama kalan
katmanlardan alınır ve consensus tarafında fundamental/sentinel modülleri
katmansız kalırsa redistribute edilir (quantum deseni). DATA_POLICY:
uydurma veri yok.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
    # F2-3 — veri yetersizliğinden düşen katman adları (flag kapalıyken hep boş).
    dropped: list[str] = field(default_factory=list)


def _drop_unavailable_enabled() -> bool:
    """`regime.drop_unavailable_layers` owner-flag'i (default KAPALI = eski davranış)."""
    try:
        from packages.data.registry.loader import load_thresholds

        return bool(
            (load_thresholds().get("regime") or {}).get("drop_unavailable_layers", False)
        )
    except Exception:
        return False  # config okunamazsa en güvenli: mevcut davranış


def _direction(score: float) -> str:
    if score >= 55:
        return "bullish"
    if score <= 45:
        return "bearish"
    return "neutral"


def _price(snap: MarketSnapshot, symbol: str) -> float | None:
    for q in snap.prices:
        if q.symbol == symbol and q.price is not None:
            return q.price
    return None


def _liquidity_layer(snap: MarketSnapshot, drop_missing: bool) -> RegimeLayer | None:
    dxy_p = _price(snap, "DXY")
    us10_p = _price(snap, "US10Y")
    us02_p = _price(snap, "US02Y")
    cpi = _price(snap, "CPI") or 0.0
    if drop_missing and (dxy_p is None or us10_p is None):
        return None  # F2-3: çekirdek girdi yok — sahte default'la skor üretme
    dxy = dxy_p if dxy_p is not None else 104.0
    us10y = us10_p if us10_p is not None else 4.3
    us02y = us02_p if us02_p is not None else 4.3
    # Yüksek DXY + yüksek getiri → likidite daralıyor.
    score = 100.0 - (dxy - 100.0) * 2.0 - (us10y - 4.0) * 5.0
    evidence = [f"DXY {dxy:.2f}", f"US10Y {us10y:.2f}%"]
    if drop_missing and us02_p is None:
        # Eğri iki GERÇEK getiri ister; yarısı uydurma eğri hesaplanmaz.
        evidence.append("2s10s veri yok — eğri sinyali atlandı")
    else:
        curve = us10y - us02y  # 2s10s getiri eğrisi spread'i
        # Ters getiri eğrisi (curve<0) → resesyon/sıkılaşma sinyali; ek ceza (cap 15).
        if curve < 0:
            score -= min(abs(curve) * 10.0, 15.0)
        evidence.append(f"2s10s {curve:+.2f}%")
    score = max(0.0, min(100.0, score))
    if cpi:
        evidence.append(f"CPI {cpi:.1f}")
    return RegimeLayer(
        name="Likidite",
        score=round(score, 1),
        direction=_direction(score),
        evidence=evidence,
    )


def _appetite_layer(snap: MarketSnapshot, drop_missing: bool) -> RegimeLayer | None:
    vix_p = _price(snap, "VIX")
    if drop_missing and vix_p is None:
        return None  # F2-3: VIX yoksa risk iştahı ölçülemez — katman düşer
    vix = vix_p if vix_p is not None else 14.0
    # Düşük VIX → risk iştahı yüksek
    score = max(0.0, min(100.0, 100.0 - (vix - 12.0) * 4.0))
    return RegimeLayer(
        name="Risk İştahı",
        score=round(score, 1),
        direction=_direction(score),
        evidence=[f"VIX {vix:.1f}"],
    )


def _crypto_layer(snap: MarketSnapshot, drop_missing: bool) -> RegimeLayer | None:
    btc_tech = snap.technicals.get("BTCUSD")
    if drop_missing and btc_tech is None:
        return None  # F2-3: BTC tekniği yoksa nötr 50 uydurulmaz
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


def _rotation_layer(snap: MarketSnapshot, drop_missing: bool) -> RegimeLayer | None:
    r = snap.rotation
    if drop_missing and r.status == "UNAVAILABLE":
        # F2-3: rotasyon verisi yetersizken provider nötr-50 placeholder döner;
        # consensus quantum'u zaten düşürüyordu — rejim katmanı da düşer.
        return None
    return RegimeLayer(
        name="Sermaye Rotasyonu",
        score=r.score,
        direction=r.direction,
        evidence=list(r.evidence),
    )


def classify(snap: MarketSnapshot) -> RegimeOutput:
    drop = _drop_unavailable_enabled()
    names = ("Likidite", "Risk İştahı", "Kripto Momentum", "Sermaye Rotasyonu")
    candidates = (
        _liquidity_layer(snap, drop),
        _appetite_layer(snap, drop),
        _crypto_layer(snap, drop),
        _rotation_layer(snap, drop),
    )
    layers = [layer for layer in candidates if layer is not None]
    dropped = [n for n, layer in zip(names, candidates, strict=True) if layer is None]
    if layers:
        avg = sum(layer.score for layer in layers) / len(layers)
    else:
        # Hiç makro katman yok: skor UYDURULMAZ; etiket en tarafsız NEUTRAL'a
        # düşer (dropped listesi durumu görünür kılar). Bu durumda fiyat verisi
        # de yok demektir → DQS zaten KILL_SWITCH bölgesindedir.
        avg = 50.0
    label: RegimeLabel
    if avg >= 65:
        label = "OFFENSIVE"
    elif avg >= 50:
        label = "NEUTRAL"
    elif avg >= 35:
        label = "DEFENSIVE"
    else:
        label = "CRISIS"
    return RegimeOutput(label=label, layers=layers, dropped=dropped)
