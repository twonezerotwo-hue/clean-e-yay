"""VWAP / Anchored VWAP Engine — top-level `analyze()` (EVIDENCE only, spec §16).

Mevcut `indicators.vwap()` (session VWAP) üzerine reclaim/rejection/deviation
durumlarını ve üç anchor noktasından (major high, major low, volume climax
candle) anchored VWAP seviyelerini ekler. `fibonacci.py`/`zones/engine.py`
ile aynı desen: pure fonksiyon, validity/diagnostics, uydurma seviye yok.

Hiçbir karar zincirine bağlı DEĞİLDİR — additive read surface.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.registry.loader import load_thresholds
from packages.data.types import AnchoredVWAPLevel, OHLCVBar, VWAPAnalysis

_DEFAULT_LOOKBACK_BARS = 60
_DEFAULT_MIN_BARS = 10
_DEFAULT_NEUTRAL_EPS = 0.0015
_DEFAULT_DEVIATION_EXTREME_PCT = 2.0
_DEFAULT_CROSS_LOOKBACK_BARS = 5


def _cfg() -> dict:
    try:
        return load_thresholds().get("vwap") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "lookback_bars": int(c.get("lookback_bars", _DEFAULT_LOOKBACK_BARS)),
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
        "neutral_eps": float(c.get("neutral_eps", _DEFAULT_NEUTRAL_EPS)),
        "deviation_extreme_pct": float(c.get("deviation_extreme_pct", _DEFAULT_DEVIATION_EXTREME_PCT)),
        "cross_lookback_bars": int(c.get("cross_lookback_bars", _DEFAULT_CROSS_LOOKBACK_BARS)),
    }


def _location(price: float, vwap_price: float, eps: float) -> str:
    if vwap_price <= 0:
        return "unknown"
    diff = (price - vwap_price) / vwap_price
    if abs(diff) <= eps:
        return "at"
    return "above" if price > vwap_price else "below"


def _anchored_level(
    window: list[OHLCVBar], anchor_idx: int, anchor_name: str, current: float, eps: float
) -> AnchoredVWAPLevel | None:
    sub = window[anchor_idx:]
    vwap_price = indicators.vwap(sub)
    if vwap_price is None or vwap_price <= 0:
        return None
    dist = abs(current - vwap_price) / current * 100.0 if current > 0 else None
    return AnchoredVWAPLevel(
        anchor=anchor_name,  # type: ignore[arg-type]
        anchor_bar_index=anchor_idx,
        vwap_price=round(vwap_price, 6),
        location=_location(current, vwap_price, eps),  # type: ignore[arg-type]
        distance_pct=round(dist, 4) if dist is not None else None,
    )


def analyze(bars: list[OHLCVBar], *, timeframe: str, current_price: float | None = None) -> VWAPAnalysis:
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return VWAPAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    window = bars[-cfg["lookback_bars"] :]
    current = current_price if current_price is not None else window[-1].close
    if current is None or current <= 0:
        diag.append("invalid_current_price")
        return VWAPAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    session_vwap = indicators.vwap(window)
    if session_vwap is None or session_vwap <= 0:
        diag.append("vwap_unavailable_missing_volume")
        return VWAPAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    eps = cfg["neutral_eps"]
    location = _location(current, session_vwap, eps)
    deviation_pct = abs(current - session_vwap) / session_vwap * 100.0
    deviation_extreme = deviation_pct >= cfg["deviation_extreme_pct"]

    # Reclaim/rejection: son `cross_lookback_bars` barda VWAP'a göre konum değişimi.
    cross_n = cfg["cross_lookback_bars"]
    start = max(0, len(window) - cross_n)
    reclaim = False
    rejection = False
    if len(window) - start >= 2:
        prior_locations = []
        for idx in range(start, len(window) - 1):
            sub = window[: idx + 1]
            v = indicators.vwap(sub)
            if v and v > 0:
                prior_locations.append(_location(window[idx].close, v, eps))
        if prior_locations:
            was_below = any(loc == "below" for loc in prior_locations)
            was_above = any(loc == "above" for loc in prior_locations)
            reclaim = was_below and location == "above"
            rejection = was_above and location == "below"

    highs = [(i, b.high) for i, b in enumerate(window)]
    lows = [(i, b.low) for i, b in enumerate(window)]
    volumes = [(i, b.volume) for i, b in enumerate(window) if b.volume is not None and b.volume >= 0]

    anchors: list[AnchoredVWAPLevel] = []
    major_high_idx = max(highs, key=lambda x: x[1])[0]
    major_low_idx = min(lows, key=lambda x: x[1])[0]
    lvl = _anchored_level(window, major_high_idx, "major_high", current, eps)
    if lvl:
        anchors.append(lvl)
    lvl = _anchored_level(window, major_low_idx, "major_low", current, eps)
    if lvl:
        anchors.append(lvl)
    if volumes:
        climax_idx = max(volumes, key=lambda x: x[1])[0]
        lvl = _anchored_level(window, climax_idx, "volume_climax", current, eps)
        if lvl:
            anchors.append(lvl)

    return VWAPAnalysis(
        timeframe=timeframe,
        session_vwap=round(session_vwap, 6),
        location=location,  # type: ignore[arg-type]
        deviation_pct=round(deviation_pct, 4),
        deviation_extreme=deviation_extreme,
        reclaim=reclaim,
        rejection=rejection,
        anchored=anchors,
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
