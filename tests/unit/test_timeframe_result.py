"""Per-timeframe technical feature builder (T-MTF) tests + architecture guards.

Deterministic synthetic bars; no wall-clock (now is passed), no network. Covers
the spec's invariant guards: missing data is a diagnostic (not a fake neutral),
there is no single aggregated score, VWAP is intraday-only, and the build is
deterministic for the same closed input.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.technical import timeframe as tf
from packages.data.types import OHLCVBar


def _bars(n, *, step, start=100.0, tf_label="1d", spacing_h=24, vol=True):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i in range(n):
        c = start + step * i
        out.append(
            OHLCVBar(
                symbol="BTCUSD",
                timeframe=tf_label,
                ts=t0 + timedelta(hours=spacing_h * i),
                open=c,
                high=c + 0.5,
                low=c - 0.5,
                close=c,
                volume=(1000.0 + i if vol else None),
                source="fixture",
            )
        )
    return out


def _now_for(bars):
    return bars[-1].ts  # last closed bar = "now" → not stale


# ── Rich result on healthy data ───────────────────────────────────────────────

def test_timeframe_result_rich_fields_uptrend():
    bars = _bars(260, step=1.0, tf_label="1d")
    r = tf.build_timeframe_result("BTCUSD", "1d", bars, now=_now_for(bars))

    assert r.status == "OK"
    assert r.data_quality.indicator_quality.rsi == "OK"
    assert r.data_quality.indicator_quality.ema200 == "OK"
    # Separate axes, both populated and directional.
    assert r.score_overview.direction_score is not None
    assert r.score_overview.direction_score > 60.0
    assert r.score_overview.strength_score is not None
    assert r.timeframe_summary.bias == "BULLISH"
    # Trend strength + regime are real (monotonic → trending).
    assert r.trend_strength.adx is not None and r.trend_strength.is_trending is True
    assert r.trend_strength.plus_di > r.trend_strength.minus_di
    assert r.volatility_regime == "TRENDING"
    # Fibonacci attached for 1d.
    assert r.fibonacci_analysis is not None


# ── Guard: missing data is a diagnostic, never a fake neutral 50 ───────────────

def test_missing_data_not_neutral():
    bars = _bars(5, step=1.0, tf_label="1h", spacing_h=1)
    r = tf.build_timeframe_result("BTCUSD", "1h", bars, now=_now_for(bars))

    assert r.score_overview.direction_score is None      # NOT 50.0
    assert r.score_overview.strength_score is None
    assert r.status == "DEGRADED"
    iq = r.data_quality.indicator_quality
    assert iq.rsi == "INSUFFICIENT_HISTORY"
    assert iq.atr == "INSUFFICIENT_HISTORY"
    assert any(w.startswith("insufficient_history") for w in r.data_quality.warnings)
    # A degraded direction still yields NEUTRAL bias, not a forced bull/bear.
    assert r.timeframe_summary.bias == "NEUTRAL"


def test_no_bars_does_not_crash_and_is_degraded():
    r = tf.build_timeframe_result("BTCUSD", "4h", [], now=datetime(2026, 6, 15, tzinfo=UTC))
    assert r.status == "DEGRADED"
    assert r.score_overview.direction_score is None
    assert "no_bars" in r.data_quality.warnings


# ── Guard: no single aggregated score for all strategies ──────────────────────

def test_no_single_score_for_all_strategies():
    bars = _bars(260, step=1.0)
    r = tf.build_timeframe_result("BTCUSD", "1d", bars, now=_now_for(bars))
    # Direction and strength are SEPARATE — there is no one collapsed score.
    assert hasattr(r.score_overview, "direction_score")
    assert hasattr(r.score_overview, "strength_score")
    assert not hasattr(r, "score")
    assert not hasattr(r, "technical_score")
    assert not hasattr(r, "aggregated_score")


# ── Guard: VWAP is intraday-only (no frontend math; per-TF semantics) ─────────

def test_vwap_only_on_intraday():
    bars_1d = _bars(260, step=1.0, tf_label="1d")
    r_1d = tf.build_timeframe_result("BTCUSD", "1d", bars_1d, now=_now_for(bars_1d))
    assert all(s.name != "above_vwap" for s in r_1d.confirmation_signals)

    bars_1h = _bars(260, step=1.0, tf_label="1h", spacing_h=1)
    r_1h = tf.build_timeframe_result("BTCUSD", "1h", bars_1h, now=_now_for(bars_1h))
    assert any(s.name == "above_vwap" for s in r_1h.confirmation_signals)


def test_fibonacci_only_for_1d_4h():
    bars_15 = _bars(260, step=1.0, tf_label="15m", spacing_h=1)
    r = tf.build_timeframe_result("BTCUSD", "15m", bars_15, now=_now_for(bars_15))
    assert r.fibonacci_analysis is None


# ── Guard: deterministic for identical closed input ───────────────────────────

def test_same_closed_input_same_output():
    bars = _bars(260, step=1.0)
    a = tf.build_timeframe_result("BTCUSD", "1d", bars, now=_now_for(bars))
    b = tf.build_timeframe_result("BTCUSD", "1d", bars, now=_now_for(bars))
    assert a.model_dump_json() == b.model_dump_json()
