"""Setup Classifier (packages/setup/classifier.py) — saf fonksiyon testleri.

Her dal en az bir testle doğrulanır; klasifikasyon hiçbir trade açmaz,
hiçbir global state okumaz — bu yüzden testler tamamen deterministik.
"""
from __future__ import annotations

from packages.setup.classifier import NO_TRADE, SetupInputs, classify

BASE = dict(
    direction_score=65.0,
    alignment_status="ALIGNED",
    is_countertrend=False,
    entry_timeframe="4h",
    volatility_regime="TRENDING",
    trend_label="TRENDING",
    is_trending=True,
    chart_pattern_names=("uptrend_structure",),
    reversal_bias="NEUTRAL",
    zone_location="mid_range",
    elliott_scenario="NO_VALID_COUNT",
    elliott_bias="unknown",
    elliott_confidence=0.0,
)


def _inputs(**overrides) -> SetupInputs:
    data = {**BASE, **overrides}
    return SetupInputs(**data)


def test_no_direction_returns_no_trade():
    result = classify(_inputs(direction_score=50.0))
    assert result.setup_type == NO_TRADE
    assert result.reason == "no_clear_direction"


def test_conflicted_alignment_returns_no_trade():
    result = classify(_inputs(alignment_status="CONFLICTED"))
    assert result.setup_type == NO_TRADE
    assert result.reason == "alignment_conflicted"


def test_breakout_long():
    result = classify(_inputs(zone_location="breakout", direction_score=70.0))
    assert result.setup_type == "BREAKOUT_LONG"
    assert result.direction == "LONG"


def test_breakdown_short():
    result = classify(_inputs(zone_location="breakdown", direction_score=30.0, chart_pattern_names=("downtrend_structure",)))
    assert result.setup_type == "BREAKOUT_SHORT"
    assert result.direction == "SHORT"


def test_reversal_long_watch_without_elliott():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_bias="unknown",
        )
    )
    assert result.setup_type == "REVERSAL_LONG_WATCH"


def test_reversal_long_confirmed_with_strong_elliott():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_scenario="C_WAVE_ENDING" if False else "ABC_CORRECTION",
            elliott_bias="REVERSAL_LONG",
            elliott_confidence=80.0,
        )
    )
    assert result.setup_type == "REVERSAL_LONG_CONFIRMED"


def test_reversal_short_watch():
    result = classify(
        _inputs(
            direction_score=35.0,
            reversal_bias="BEARISH",
            zone_location="near_resistance",
        )
    )
    assert result.setup_type == "REVERSAL_SHORT_WATCH"


def test_range_long():
    result = classify(
        _inputs(
            direction_score=55.0,
            volatility_regime="RANGING",
            is_trending=False,
            chart_pattern_names=(),
        )
    )
    assert result.setup_type == "RANGE_LONG"


def test_range_via_ranging_pattern():
    result = classify(
        _inputs(
            direction_score=55.0,
            volatility_regime="UNKNOWN",
            is_trending=False,
            chart_pattern_names=("ranging",),
        )
    )
    assert result.setup_type == "RANGE_LONG"


def test_pullback_long():
    result = classify(
        _inputs(
            direction_score=60.0,
            is_trending=True,
            is_countertrend=True,
            chart_pattern_names=("uptrend_structure",),
        )
    )
    assert result.setup_type == "PULLBACK_LONG"


def test_scalp_long_on_short_timeframe():
    result = classify(
        _inputs(
            direction_score=60.0,
            entry_timeframe="15m",
            is_trending=False,
            chart_pattern_names=(),
        )
    )
    assert result.setup_type == "SCALP_LONG"


def test_trend_long():
    result = classify(_inputs())
    assert result.setup_type == "TREND_LONG"


def test_trend_short():
    result = classify(
        _inputs(
            direction_score=35.0,
            chart_pattern_names=("downtrend_structure",),
        )
    )
    assert result.setup_type == "TREND_SHORT"


def test_no_setup_evidence_matched_falls_back_to_no_trade():
    result = classify(
        _inputs(
            direction_score=60.0,
            is_trending=False,
            entry_timeframe="1d",
            chart_pattern_names=(),
            volatility_regime="UNKNOWN",
        )
    )
    assert result.setup_type == NO_TRADE
    assert result.reason == "no_setup_evidence_matched"


# --- Faz 4: alternatif onay kaynakları (Elliott olmadan da REVERSAL_*_CONFIRMED) ---


def test_reversal_confirmed_by_liquidity_sweep_without_elliott():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_bias="unknown",
            liquidity_sweep_bias="REVERSAL_LONG",
        )
    )
    assert result.setup_type == "REVERSAL_LONG_CONFIRMED"
    assert any("liquidity_sweep" in e for e in result.evidence)


def test_reversal_confirmed_by_exhaustion_extreme():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_bias="unknown",
            exhaustion_score=10.0,
        )
    )
    assert result.setup_type == "REVERSAL_LONG_CONFIRMED"


def test_reversal_confirmed_by_volume_climax_capitulation():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_bias="unknown",
            volume_state="VOLUME_CLIMAX",
            volume_price_direction="down",
        )
    )
    assert result.setup_type == "REVERSAL_LONG_CONFIRMED"


def test_reversal_watch_when_no_confirmation_source_matches():
    result = classify(
        _inputs(
            direction_score=60.0,
            reversal_bias="BULLISH",
            zone_location="near_support",
            elliott_bias="unknown",
            liquidity_sweep_bias="unknown",
            exhaustion_score=50.0,
            volume_state="VOLUME_NEUTRAL",
        )
    )
    assert result.setup_type == "REVERSAL_LONG_WATCH"
