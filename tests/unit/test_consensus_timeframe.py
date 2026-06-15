"""Cross-timeframe consensus (T2) tests + architecture guards.

Inputs are constructed TechnicalTimeframeResult models (deterministic, no network)
so each alignment / countertrend / dilution scenario is exact. Covers the spec
guards: no single aggregated score, and conditional countertrend.
"""
from __future__ import annotations

from packages.consensus import timeframe as cons
from packages.data.types import (
    ConfirmationSignal,
    TechnicalDataQuality,
    TechnicalKeyLevels,
    TechnicalScoreOverview,
    TechnicalTimeframeResult,
    TechnicalTimeframeSummary,
    Timeframe,
)


def _tfr(
    tf: Timeframe,
    bias: str,
    *,
    direction: float = 70.0,
    strength: float = 70.0,
    status: str = "OK",
    support=None,
    resistance=None,
    fired: bool = True,
) -> TechnicalTimeframeResult:
    degraded = status == "DEGRADED"
    return TechnicalTimeframeResult(
        symbol="BTCUSD",
        timeframe=tf,
        data_quality=TechnicalDataQuality(status=status, bars_used=260),
        score_overview=TechnicalScoreOverview(
            direction_score=None if degraded else direction,
            strength_score=None if degraded else strength,
        ),
        key_levels=TechnicalKeyLevels(support=support, resistance=resistance),
        confirmation_signals=[ConfirmationSignal(name="macd_histogram_positive", fired=fired)],
        timeframe_summary=TechnicalTimeframeSummary(bias=bias),
        status=status,
    )


def test_aligned_uptrend():
    per_tf = {
        "1d": _tfr("1d", "BULLISH"),
        "4h": _tfr("4h", "BULLISH"),
        "1h": _tfr("1h", "BULLISH"),
    }
    snap = cons.build_consensus("BTCUSD", per_tf)
    assert snap.alignment_status == "ALIGNED"
    assert snap.alignment_score == 100.0
    assert snap.agreement_score == 100.0
    assert snap.direction_score == 70.0
    assert snap.is_countertrend is False
    assert snap.confirmed_count == 3
    assert snap.per_timeframe_bias == {"d1": "BULLISH", "h4": "BULLISH", "h1": "BULLISH"}


def test_countertrend_is_conditional():
    # Opposite higher (1d bull) vs lower (1h bear) → countertrend.
    opp = cons.build_consensus(
        "BTCUSD",
        {"1d": _tfr("1d", "BULLISH"), "1h": _tfr("1h", "BEARISH", direction=30.0)},
    )
    assert opp.is_countertrend is True
    assert opp.alignment_status == "COUNTERTREND"

    # Same direction across TFs → trend-aligned, NOT countertrend.
    same = cons.build_consensus(
        "BTCUSD",
        {"1d": _tfr("1d", "BULLISH"), "1h": _tfr("1h", "BULLISH", direction=65.0)},
    )
    assert same.is_countertrend is False
    assert same.alignment_status == "ALIGNED"


def test_neutral_dilutes_alignment():
    per_tf = {
        "1d": _tfr("1d", "BULLISH", direction=70.0),
        "4h": _tfr("4h", "NEUTRAL", direction=50.0, strength=10.0),
        "1h": _tfr("1h", "NEUTRAL", direction=50.0, strength=10.0),
    }
    snap = cons.build_consensus("BTCUSD", per_tf)
    # One bullish + two neutral → alignment magnitude diluted toward 0.
    assert 30.0 <= snap.alignment_score <= 40.0          # ~33.3
    assert snap.agreement_score == 100.0                 # of the directional TFs, unanimous
    assert snap.alignment_status == "PARTIAL"


def test_conflict_without_clean_higher_lower_is_conflicted():
    # higher(1d) and lower(1h) agree (both bull) but a middle TF disagrees → CONFLICTED, not countertrend.
    per_tf = {
        "1d": _tfr("1d", "BULLISH"),
        "4h": _tfr("4h", "BEARISH", direction=25.0),
        "1h": _tfr("1h", "BULLISH"),
    }
    snap = cons.build_consensus("BTCUSD", per_tf)
    assert snap.is_countertrend is False
    assert snap.alignment_status == "CONFLICTED"


def test_degraded_tf_is_blocking_not_neutral():
    per_tf = {
        "1d": _tfr("1d", "BULLISH"),
        "4h": _tfr("4h", "NEUTRAL", status="DEGRADED"),
    }
    snap = cons.build_consensus("BTCUSD", per_tf)
    assert snap.blocking_count == 1
    assert snap.direction_score == 70.0   # only the valid 1d contributes
    # degraded TF still appears in the bias map (transparency) but is not scored.
    assert snap.per_timeframe_bias["h4"] == "NEUTRAL"


def test_cross_timeframe_confluence_clusters_two_tfs():
    per_tf = {
        "1d": _tfr("1d", "BULLISH", support=100.0),
        "4h": _tfr("4h", "BULLISH", support=100.5),   # within 1% of 100.0
        "1h": _tfr("1h", "BULLISH", support=130.0),   # far away → no cluster
    }
    snap = cons.build_consensus("BTCUSD", per_tf)
    zones = [z for z in snap.cross_timeframe_confluence if z.kind == "support"]
    assert len(zones) == 1
    assert set(zones[0].timeframes) == {"d1", "h4"}


def test_no_single_score_for_all_strategies():
    snap = cons.build_consensus("BTCUSD", {"1d": _tfr("1d", "BULLISH")})
    for axis in ("direction_score", "strength_score", "agreement_score", "alignment_score"):
        assert hasattr(snap, axis)
    assert not hasattr(snap, "score")
    assert not hasattr(snap, "technical_score")
    assert not hasattr(snap, "aggregated_score")


def test_all_degraded_is_partial_no_direction():
    per_tf = {"1d": _tfr("1d", "NEUTRAL", status="DEGRADED")}
    snap = cons.build_consensus("BTCUSD", per_tf)
    assert snap.direction_score is None
    assert snap.blocking_count == 1
    assert snap.alignment_status == "PARTIAL"
