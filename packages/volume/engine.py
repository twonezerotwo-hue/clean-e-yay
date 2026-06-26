"""Volume Validation Engine — top-level `analyze()` (EVIDENCE only, spec §15).

Gerçek OHLCV barlarındaki hacim/fiyat ilişkisini beş duruma (VOLUME_CLIMAX,
VOLUME_CONFIRMATION, VOLUME_WEAKENING, VOLUME_CONFLICT, VOLUME_NEUTRAL)
indirger. `fibonacci.py`/`elliott/engine.py`/`zones/engine.py` ile aynı
deseni izler: pure fonksiyon, validity/diagnostics, uydurma değer yok.

Hiçbir karar zincirine bağlı DEĞİLDİR — additive read surface.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.data.types import OHLCVBar, VolumeAnalysis

_DEFAULT_LOOKBACK_BARS = 20
_DEFAULT_MIN_BARS = 10
_DEFAULT_CLIMAX_RATIO = 2.0
_DEFAULT_CONFIRMATION_RATIO = 1.2
_DEFAULT_WEAKENING_RATIO = 0.7


def _cfg() -> dict:
    try:
        return load_thresholds().get("volume_validation") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "lookback_bars": int(c.get("lookback_bars", _DEFAULT_LOOKBACK_BARS)),
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
        "climax_ratio": float(c.get("climax_ratio", _DEFAULT_CLIMAX_RATIO)),
        "confirmation_ratio": float(c.get("confirmation_ratio", _DEFAULT_CONFIRMATION_RATIO)),
        "weakening_ratio": float(c.get("weakening_ratio", _DEFAULT_WEAKENING_RATIO)),
    }


def _direction(delta: float, eps: float = 1e-9) -> str:
    if delta > eps:
        return "up"
    if delta < -eps:
        return "down"
    return "flat"


def analyze(bars: list[OHLCVBar], *, timeframe: str) -> VolumeAnalysis:
    """Son barın hacim/fiyat ilişkisini, önceki pencereye göre sınıflandırır."""
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return VolumeAnalysis(timeframe=timeframe, validity="unavailable", diagnostics=diag)

    window = bars[-cfg["lookback_bars"] :]
    last = window[-1]
    prior = window[:-1]

    volumes = [b.volume for b in prior if b.volume is not None and b.volume >= 0]
    if last.volume is None or last.volume < 0 or len(volumes) < 3:
        diag.append("missing_or_invalid_volume")
        return VolumeAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    avg_prior = sum(volumes) / len(volumes)
    if avg_prior <= 0:
        diag.append("zero_average_volume")
        return VolumeAnalysis(timeframe=timeframe, validity="weak", diagnostics=diag)

    ratio = last.volume / avg_prior
    price_dir = _direction(last.close - last.open)
    trend_dir = _direction(last.close - window[0].close)

    if ratio >= cfg["climax_ratio"]:
        state = "VOLUME_CLIMAX"
    elif ratio >= cfg["confirmation_ratio"] and price_dir == trend_dir and trend_dir != "flat":
        state = "VOLUME_CONFIRMATION"
    elif ratio >= cfg["confirmation_ratio"] and price_dir != trend_dir and price_dir != "flat" and trend_dir != "flat":
        state = "VOLUME_CONFLICT"
    elif ratio <= cfg["weakening_ratio"] and trend_dir != "flat":
        state = "VOLUME_WEAKENING"
    else:
        state = "VOLUME_NEUTRAL"

    return VolumeAnalysis(
        timeframe=timeframe,
        state=state,  # type: ignore[arg-type]
        volume_ratio=round(ratio, 3),
        price_direction=price_dir,  # type: ignore[arg-type]
        trend_direction=trend_dir,  # type: ignore[arg-type]
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
