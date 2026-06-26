"""Location Score — top-level `analyze()` (EVIDENCE only, spec §18).

Zone Engine (zorunlu girdi) + Fibonacci + VWAP + Liquidity Sweep (opsiyonel
girdiler) kanıtlarını birleştirip 0-100 tek bir "giriş kalitesi" skoruna
indirger. Supply/demand zone Zone Engine'in kapsamı dışında olduğu için
buraya da girmez (bilinçli sınırlama, uydurma kanıt eklenmez).

Bu modül bar okumaz — sadece zaten hesaplanmış analiz nesnelerini (pure
composition) birleştirir. Hiçbir karar zincirine bağlı DEĞİLDİR.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.data.types import (
    FibonacciAnalysis,
    LiquiditySweepAnalysis,
    LocationScoreAnalysis,
    VWAPAnalysis,
    ZoneAnalysis,
)

_DEFAULT_GOOD_LOCATION_MIN = 70.0
_DEFAULT_MID_RANGE_MIN = 40.0

_ZONE_BASE_SCORE = {
    "near_support": 80.0,
    "near_resistance": 80.0,
    "breakout": 65.0,
    "breakdown": 65.0,
    "mid_range": 35.0,
    "unknown": 50.0,
}

_FIB_CONFLUENCE_BONUS = 10.0
_VWAP_EVENT_BONUS = 5.0
_SWEEP_RECLAIM_BONUS = 10.0


def _cfg() -> dict:
    try:
        return load_thresholds().get("location_score") or {}
    except (OSError, KeyError, ValueError):
        return {}


def _config() -> dict:
    c = _cfg()
    return {
        "good_location_min": float(c.get("good_location_min", _DEFAULT_GOOD_LOCATION_MIN)),
        "mid_range_min": float(c.get("mid_range_min", _DEFAULT_MID_RANGE_MIN)),
    }


def _classify(score: float, cfg: dict) -> str:
    if score >= cfg["good_location_min"]:
        return "GOOD_LOCATION"
    if score >= cfg["mid_range_min"]:
        return "MID_RANGE"
    return "BAD_LOCATION"


def analyze(
    zone: ZoneAnalysis,
    *,
    fib: FibonacciAnalysis | None = None,
    vwap: VWAPAnalysis | None = None,
    sweep: LiquiditySweepAnalysis | None = None,
) -> LocationScoreAnalysis:
    cfg = _config()
    diag: list[str] = []

    if zone.validity == "unavailable":
        diag.append("zone_unavailable")
        return LocationScoreAnalysis(score=50.0, location_class="unknown", validity="unavailable", diagnostics=diag)

    score = _ZONE_BASE_SCORE.get(zone.location, 50.0)
    contributions = [f"zone_location:{zone.location}={score:.0f}"]

    if fib is not None and fib.zone in ("near_support", "near_resistance"):
        score += _FIB_CONFLUENCE_BONUS
        contributions.append("fib_confluence")

    if vwap is not None and (vwap.reclaim or vwap.rejection):
        score += _VWAP_EVENT_BONUS
        contributions.append("vwap_reclaim" if vwap.reclaim else "vwap_rejection")

    if sweep is not None and sweep.state in ("LOW_SWEEP_RECLAIMED", "HIGH_SWEEP_RECLAIMED"):
        score += _SWEEP_RECLAIM_BONUS
        contributions.append("liquidity_sweep_reclaimed")

    score = max(0.0, min(100.0, score))

    return LocationScoreAnalysis(
        score=round(score, 1),
        location_class=_classify(score, cfg),  # type: ignore[arg-type]
        contributions=contributions,
        validity="sane",
        diagnostics=diag,
    )


__all__ = ["analyze"]
