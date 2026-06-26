"""Trigger Engine — top-level `analyze()` (EVIDENCE only, spec §22).

Mum formasyonu (bullish/bearish engulfing, pin bar) + hacim teyidi
(opsiyonel `VolumeAnalysis`) + VWAP reclaim/rejection (opsiyonel
`VWAPAnalysis`) + liquidity sweep reclaim (opsiyonel `LiquiditySweepAnalysis`)
kanıtlarını ağırlıklı toplayıp tek bir trigger_score (0-100) ve
TRIGGER_CONFIRMED/MISSING/FAILED durumuna indirger.

Hiçbir karar zincirine bağlı DEĞİLDİR — additive read surface.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.data.types import (
    LiquiditySweepAnalysis,
    OHLCVBar,
    TriggerAnalysis,
    VolumeAnalysis,
    VWAPAnalysis,
)

_DEFAULT_MIN_BARS = 3
_DEFAULT_CONFIRMED_MIN = 70.0
_DEFAULT_PIN_BAR_WICK_RATIO = 2.0  # wick >= body * ratio

_WEIGHT_ENGULFING = 30.0
_WEIGHT_PIN_BAR = 25.0
_WEIGHT_VOLUME_CONFIRMATION = 20.0
_WEIGHT_VWAP_EVENT = 15.0
_WEIGHT_SWEEP_RECLAIM = 20.0


def _cfg() -> dict:
    try:
        return load_thresholds().get("trigger_engine") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "min_bars": int(c.get("min_bars", _DEFAULT_MIN_BARS)),
        "confirmed_min": float(c.get("confirmed_min", _DEFAULT_CONFIRMED_MIN)),
        "pin_bar_wick_ratio": float(c.get("pin_bar_wick_ratio", _DEFAULT_PIN_BAR_WICK_RATIO)),
    }


def _engulfing(prev: OHLCVBar, last: OHLCVBar) -> str | None:
    prev_bearish = prev.close < prev.open
    prev_bullish = prev.close > prev.open
    last_bullish = last.close > last.open
    last_bearish = last.close < last.open
    if prev_bearish and last_bullish and last.open <= prev.close and last.close >= prev.open:
        return "bullish"
    if prev_bullish and last_bearish and last.open >= prev.close and last.close <= prev.open:
        return "bearish"
    return None


def _pin_bar(bar: OHLCVBar, wick_ratio: float) -> str | None:
    body = abs(bar.close - bar.open)
    upper_wick = bar.high - max(bar.close, bar.open)
    lower_wick = min(bar.close, bar.open) - bar.low
    if body <= 0:
        return None
    if lower_wick >= body * wick_ratio and upper_wick < body:
        return "bullish"
    if upper_wick >= body * wick_ratio and lower_wick < body:
        return "bearish"
    return None


def analyze(
    bars: list[OHLCVBar],
    *,
    timeframe: str,
    volume: VolumeAnalysis | None = None,
    vwap: VWAPAnalysis | None = None,
    sweep: LiquiditySweepAnalysis | None = None,
) -> TriggerAnalysis:
    cfg = _config()
    diag: list[str] = []

    if not bars or len(bars) < cfg["min_bars"]:
        diag.append(f"insufficient_bars:{len(bars) if bars else 0}")
        return TriggerAnalysis(timeframe=timeframe, state="TRIGGER_MISSING", validity="unavailable", diagnostics=diag)

    prev, last = bars[-2], bars[-1]
    score = 0.0
    matched: list[str] = []
    pattern_direction: str | None = None

    engulf = _engulfing(prev, last)
    if engulf is not None:
        score += _WEIGHT_ENGULFING
        matched.append(f"engulfing_{engulf}")
        pattern_direction = engulf

    pin = _pin_bar(last, cfg["pin_bar_wick_ratio"])
    if pin is not None:
        score += _WEIGHT_PIN_BAR
        matched.append(f"pin_bar_{pin}")
        pattern_direction = pattern_direction or pin

    contradiction = False
    if volume is not None and volume.state == "VOLUME_CONFIRMATION":
        score += _WEIGHT_VOLUME_CONFIRMATION
        matched.append("volume_confirmation")
    elif volume is not None and volume.state == "VOLUME_CONFLICT" and pattern_direction is not None:
        opposite = (pattern_direction == "bullish" and volume.price_direction == "down") or (
            pattern_direction == "bearish" and volume.price_direction == "up"
        )
        if opposite:
            contradiction = True
            diag.append("volume_conflict_against_pattern")

    if vwap is not None and (vwap.reclaim or vwap.rejection):
        score += _WEIGHT_VWAP_EVENT
        matched.append("vwap_reclaim" if vwap.reclaim else "vwap_rejection")

    if sweep is not None and sweep.state in ("LOW_SWEEP_RECLAIMED", "HIGH_SWEEP_RECLAIMED"):
        score += _WEIGHT_SWEEP_RECLAIM
        matched.append("liquidity_sweep_reclaimed")

    score = max(0.0, min(100.0, score))

    if contradiction:
        state = "TRIGGER_FAILED"
    elif score >= cfg["confirmed_min"]:
        state = "TRIGGER_CONFIRMED"
    else:
        state = "TRIGGER_MISSING"

    return TriggerAnalysis(
        timeframe=timeframe,
        state=state,  # type: ignore[arg-type]
        trigger_score=round(score, 1),
        matched_triggers=matched,
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
