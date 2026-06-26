"""Zone Engine — top-level `analyze()` (EVIDENCE only).

Yakın fraktal swing pivotlarını (mevcut, dokunulmayan
`packages/data/providers/technical/indicators.py::swing_pivots`) kümeleyerek
support/resistance BÖLGELERİ üretir — tek seviye değil, fiyat aralığı (spec
§12). `fibonacci.py` ile aynı deseni izler: pure fonksiyon, validity/
diagnostics, uydurma seviye yok.

Supply/demand zone tespiti bu sürümün kapsamı DIŞINDADIR — ayrı bir iştir,
bilinçli olarak eklenmedi (DATA_POLICY: yarım/uydurma kanıt üretmemek için
açıkça not edilir, "unavailable" gibi davranılmaz).

Henüz hiçbir canlı karar zincirine (decide_for_symbol / decide_matrix /
agent_pipeline) bağlı DEĞİLDİR — Elliott motoruyla aynı "additive read
surface" ilkesi: sadece read-only API yüzeyinden erişilir.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.registry.loader import load_thresholds
from packages.data.types import OHLCVBar, PriceZone, ZoneAnalysis

_DEFAULT_LOOKBACK_BARS = 120
_DEFAULT_MIN_BARS = 20
_DEFAULT_PIVOT_LEFT = 3
_DEFAULT_PIVOT_RIGHT = 3
_DEFAULT_CLUSTER_PROXIMITY_PCT = 1.0  # bu yüzdeden yakın pivotlar tek bölgede birleşir


def _cfg() -> dict:
    try:
        return load_thresholds().get("zones") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "lookback_bars": int(c.get("lookback_bars", _DEFAULT_LOOKBACK_BARS)),
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
        "pivot_left": int(c.get("pivot_left", _DEFAULT_PIVOT_LEFT)),
        "pivot_right": int(c.get("pivot_right", _DEFAULT_PIVOT_RIGHT)),
        "cluster_proximity_pct": float(
            c.get("cluster_proximity_pct", _DEFAULT_CLUSTER_PROXIMITY_PCT)
        ),
    }


def _cluster(prices: list[float], kind: str, proximity_pct: float) -> list[PriceZone]:
    """Yakın fiyatları (≤ proximity_pct göreceli mesafe) bir bölgede birleştir.

    Uydurma seviye yok: girdi pivot fiyatlarının min/max'ı bölgenin
    price_low/price_high'ını belirler; touches = o bölgeye düşen pivot sayısı.
    """
    if not prices:
        return []
    ordered = sorted(prices)
    clusters: list[list[float]] = [[ordered[0]]]
    for p in ordered[1:]:
        last_cluster = clusters[-1]
        ref = last_cluster[-1]
        rel = abs(p - ref) / ref * 100.0 if ref > 0 else 0.0
        if rel <= proximity_pct:
            last_cluster.append(p)
        else:
            clusters.append([p])
    return [
        PriceZone(
            kind=kind,  # type: ignore[arg-type]
            price_low=round(min(c), 6),
            price_high=round(max(c), 6),
            touches=len(c),
        )
        for c in clusters
    ]


def _location(
    current: float, range_high: float, range_low: float, nearest: PriceZone | None, proximity_pct: float
) -> str:
    if current > range_high:
        return "breakout"
    if current < range_low:
        return "breakdown"
    if nearest is not None and nearest.distance_pct is not None and nearest.distance_pct <= proximity_pct:
        return "near_support" if nearest.kind == "support" else "near_resistance"
    return "mid_range"


def analyze(
    bars: list[OHLCVBar],
    *,
    timeframe: str,
    current_price: float | None = None,
) -> ZoneAnalysis:
    """Deterministik support/resistance zone analizi (uydurma seviye yok)."""
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return ZoneAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    window = bars[-cfg["lookback_bars"] :]
    current = current_price if current_price is not None else window[-1].close
    if current is None or current <= 0:
        diag.append("invalid_current_price")
        return ZoneAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    pivots = indicators.swing_pivots(window, left=cfg["pivot_left"], right=cfg["pivot_right"])
    if pivots is None:
        diag.append("insufficient_pivots")
        return ZoneAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    highs, lows = pivots
    if not highs and not lows:
        diag.append("no_pivots_found")
        return ZoneAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    proximity = cfg["cluster_proximity_pct"]
    resistance_zones = _cluster(highs, "resistance", proximity)
    support_zones = _cluster(lows, "support", proximity)
    zones = resistance_zones + support_zones

    for z in zones:
        z.distance_pct = round(
            abs(((z.price_low + z.price_high) / 2.0) - current) / current * 100.0, 4
        )
    nearest = min(zones, key=lambda z: z.distance_pct or 0.0) if zones else None

    range_high = max([b.high for b in window], default=current)
    range_low = min([b.low for b in window], default=current)

    location = _location(current, range_high, range_low, nearest, proximity)

    return ZoneAnalysis(
        timeframe=timeframe,
        zones=zones,
        nearest_zone=nearest,
        location=location,  # type: ignore[arg-type]
        range_high=round(range_high, 6),
        range_low=round(range_low, 6),
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
