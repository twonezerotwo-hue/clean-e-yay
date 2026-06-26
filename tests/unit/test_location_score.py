from __future__ import annotations

from packages.data.types import FibonacciAnalysis, LiquiditySweepAnalysis, VWAPAnalysis, ZoneAnalysis
from packages.scoring import location


def _zone(loc: str, validity: str = "sane") -> ZoneAnalysis:
    return ZoneAnalysis(timeframe="1d", location=loc, validity=validity)  # type: ignore[arg-type]


def test_unavailable_zone_yields_unknown():
    result = location.analyze(_zone("unknown", validity="unavailable"))
    assert result.validity == "unavailable"
    assert result.location_class == "unknown"


def test_near_support_is_good_location():
    result = location.analyze(_zone("near_support"))
    assert result.location_class == "GOOD_LOCATION"
    assert result.score == 80.0


def test_mid_range_is_bad_or_mid():
    result = location.analyze(_zone("mid_range"))
    assert result.location_class in ("MID_RANGE", "BAD_LOCATION")
    assert result.score == 35.0


def test_fib_confluence_boosts_score():
    fib = FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane")
    result = location.analyze(_zone("near_support"), fib=fib)
    assert result.score == 90.0
    assert "fib_confluence" in result.contributions


def test_vwap_reclaim_boosts_score():
    vwap = VWAPAnalysis(timeframe="1d", reclaim=True, validity="sane")
    result = location.analyze(_zone("near_support"), vwap=vwap)
    assert result.score == 85.0
    assert "vwap_reclaim" in result.contributions


def test_sweep_reclaim_boosts_score_and_clamps_at_100():
    sweep = LiquiditySweepAnalysis(timeframe="1d", state="LOW_SWEEP_RECLAIMED", validity="sane")
    fib = FibonacciAnalysis(timeframe="1D", zone="near_support", validity="sane")
    vwap = VWAPAnalysis(timeframe="1d", reclaim=True, validity="sane")
    result = location.analyze(_zone("near_support"), fib=fib, vwap=vwap, sweep=sweep)
    assert result.score == 100.0  # 80+10+5+10=105 clamped
    assert result.location_class == "GOOD_LOCATION"
