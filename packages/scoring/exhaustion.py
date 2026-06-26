"""Exhaustion Score — top-level `analyze()` (EVIDENCE only, spec §17).

Yön skoru DEĞİLDİR — hareketin yorulup yorulmadığını ölçer (0 = downside
exhaustion / long reversal bölgesi, 50 = nötr, 100 = upside exhaustion /
short reversal bölgesi). RSI extreme, son-N-bar getirisi, volume climax
(opsiyonel `VolumeAnalysis` girdisi) ve liquidity sweep (opsiyonel
`LiquiditySweepAnalysis` girdisi) kanıtlarını birleştirir.

`fibonacci.py`/`zones/engine.py` ile aynı desen: pure fonksiyon, validity/
diagnostics, uydurma değer yok. Hiçbir karar zincirine bağlı DEĞİLDİR.
"""
from __future__ import annotations

from packages.data.providers.technical import indicators
from packages.data.registry.loader import load_thresholds
from packages.data.types import ExhaustionAnalysis, LiquiditySweepAnalysis, OHLCVBar, VolumeAnalysis

_DEFAULT_MIN_BARS = 20
_DEFAULT_RETURN_LOOKBACK_BARS = 5
_DEFAULT_RSI_EXTREME_HIGH = 70.0
_DEFAULT_RSI_EXTREME_LOW = 30.0
_DEFAULT_RETURN_EXTREME_PCT = 5.0
_RSI_WEIGHT = 25.0
_RETURN_WEIGHT = 15.0
_VOLUME_CLIMAX_WEIGHT = 10.0
_SWEEP_WEIGHT = 15.0


def _cfg() -> dict:
    try:
        return load_thresholds().get("exhaustion") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
        "return_lookback_bars": int(c.get("return_lookback_bars", _DEFAULT_RETURN_LOOKBACK_BARS)),
        "rsi_extreme_high": float(c.get("rsi_extreme_high", _DEFAULT_RSI_EXTREME_HIGH)),
        "rsi_extreme_low": float(c.get("rsi_extreme_low", _DEFAULT_RSI_EXTREME_LOW)),
        "return_extreme_pct": float(c.get("return_extreme_pct", _DEFAULT_RETURN_EXTREME_PCT)),
    }


def analyze(
    bars: list[OHLCVBar],
    *,
    timeframe: str,
    volume: VolumeAnalysis | None = None,
    sweep: LiquiditySweepAnalysis | None = None,
) -> ExhaustionAnalysis:
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return ExhaustionAnalysis(timeframe=timeframe, score=50.0, validity="unavailable", diagnostics=diag)

    closes = [b.close for b in bars]
    rsi_v = indicators.rsi(closes)

    lb = cfg["return_lookback_bars"]
    recent_return_pct = None
    if len(bars) > lb and bars[-1 - lb].close > 0:
        recent_return_pct = (bars[-1].close - bars[-1 - lb].close) / bars[-1 - lb].close * 100.0

    score = 50.0
    contributions: list[str] = []

    if rsi_v is not None:
        if rsi_v >= cfg["rsi_extreme_high"]:
            score += _RSI_WEIGHT
            contributions.append(f"rsi_extreme_high:{rsi_v:.1f}")
        elif rsi_v <= cfg["rsi_extreme_low"]:
            score -= _RSI_WEIGHT
            contributions.append(f"rsi_extreme_low:{rsi_v:.1f}")
    else:
        diag.append("rsi_unavailable")

    if recent_return_pct is not None:
        if recent_return_pct >= cfg["return_extreme_pct"]:
            score += _RETURN_WEIGHT
            contributions.append(f"extended_up_return:{recent_return_pct:.2f}pct")
        elif recent_return_pct <= -cfg["return_extreme_pct"]:
            score -= _RETURN_WEIGHT
            contributions.append(f"extended_down_return:{recent_return_pct:.2f}pct")

    if volume is not None and volume.state == "VOLUME_CLIMAX":
        if volume.price_direction == "up":
            score += _VOLUME_CLIMAX_WEIGHT
            contributions.append("volume_climax_up")
        elif volume.price_direction == "down":
            score -= _VOLUME_CLIMAX_WEIGHT
            contributions.append("volume_climax_down")

    if sweep is not None:
        if sweep.state == "HIGH_SWEEP_RECLAIMED":
            score += _SWEEP_WEIGHT
            contributions.append("high_sweep_reclaimed")
        elif sweep.state == "LOW_SWEEP_RECLAIMED":
            score -= _SWEEP_WEIGHT
            contributions.append("low_sweep_reclaimed")

    score = max(0.0, min(100.0, score))

    return ExhaustionAnalysis(
        timeframe=timeframe,
        score=round(score, 1),
        rsi=round(rsi_v, 2) if rsi_v is not None else None,
        recent_return_pct=round(recent_return_pct, 4) if recent_return_pct is not None else None,
        contributions=contributions,
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
