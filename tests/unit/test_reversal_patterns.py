"""Step §4.5 — reversal + chart-pattern detection (EVIDENCE only, from real bars).

Deterministic: bars are built from explicit close sequences with well-spaced fractal
pivots so each detection path is exercised. Insufficient history → None (the field is
absent, never a fabricated value — DATA_POLICY).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.technical import patterns, reversal, timeframe
from packages.data.types import OHLCVBar


def _bars(closes: list[float]) -> list[OHLCVBar]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol="X", timeframe="1d", ts=base + timedelta(days=i),
            open=c, high=c + 0.5, low=c - 0.5, close=c, volume=1000.0, source="test",
        )
        for i, c in enumerate(closes)
    ]


# Ascending zigzag — clean higher-highs + higher-lows.
_UP = [100, 104, 108, 110, 108, 106, 108, 112, 116, 114, 112, 116, 120, 122, 120, 118,
       120, 124, 128, 126, 124, 128, 132, 134, 132, 130, 132, 136, 140, 138]
_DOWN = [200 - c for c in _UP]  # mirror → lower-highs + lower-lows
_RANGE = ([100, 104, 108, 110, 108, 104, 100, 104, 108, 110, 108, 104] * 3)


# ── chart patterns: swing structure ───────────────────────────────────────────

def test_uptrend_structure_is_bullish():
    p = patterns.detect(_bars(_UP), left=2, right=2)
    assert p is not None
    assert p.active_patterns[0].name == "uptrend_structure"
    assert p.bias == "BULLISH"


def test_downtrend_structure_is_bearish():
    p = patterns.detect(_bars(_DOWN), left=2, right=2)
    assert p is not None and p.active_patterns[0].name == "downtrend_structure"
    assert p.bias == "BEARISH"


def test_ranging_when_structure_mixed():
    p = patterns.detect(_bars(_RANGE), left=2, right=2)
    assert p is not None and p.active_patterns[0].name == "ranging"
    assert p.bias == "NEUTRAL"


def test_patterns_none_when_insufficient_bars():
    assert patterns.detect(_bars(_UP[:8]), left=2, right=2) is None


# ── reversal: momentum divergence ─────────────────────────────────────────────

def _bullish_div_bars() -> list[OHLCVBar]:
    # Price makes a lower low while downside momentum fades (RSI higher low).
    closes = []
    p = 200.0
    for i in range(60):
        p = p - (3.0 if i < 30 else 0.3) + (2.5 if i % 5 < 2 else -2.0)
        closes.append(max(p, 10.0))
    return _bars(closes)


def test_rsi_bullish_divergence_detected():
    r = reversal.detect(_bullish_div_bars(), left=2, right=2)
    assert r is not None
    assert any(s.type == "rsi_bullish_divergence" for s in r.signals)
    assert r.bias == "BULLISH"


def test_rsi_bearish_divergence_detected():
    # Mirror of the bullish case: price keeps making higher highs while upside
    # momentum fades (steep rise first half, shallow rise second half).
    closes = []
    p = 50.0
    for i in range(60):
        p = p + (3.0 if i < 30 else 0.3) + (2.0 if i % 5 < 2 else -1.0)
        closes.append(p)
    r = reversal.detect(_bars(closes), left=2, right=2)
    assert r is not None
    assert any(s.type == "rsi_bearish_divergence" for s in r.signals)
    assert r.bias == "BEARISH"


def test_reversal_none_when_insufficient_bars():
    assert reversal.detect(_bars(_UP[:10]), left=2, right=2) is None


def test_reversal_neutral_when_no_signal():
    # A clean monotonic ramp has no divergence and no double formation.
    r = reversal.detect(_bars([100 + i for i in range(40)]), left=2, right=2)
    assert r is not None and r.bias == "NEUTRAL" and r.signals == []


# ── double formations ─────────────────────────────────────────────────────────

def test_double_bottom_detected():
    # Two near-equal lows (~100) with a peak (~112) between them → bullish.
    closes = [110, 106, 102, 100, 102, 106, 110, 112, 110, 106, 102, 100.5, 102, 106, 110]
    closes = [120, 116] + closes + [114, 118]  # pad for warm-up / pivots
    r = reversal.detect(_bars(closes * 2), left=2, right=2)
    assert r is not None
    assert any(s.type == "double_bottom" for s in r.signals)


# ── builder wiring (EVIDENCE attached; insufficient → None) ────────────────────

def test_builder_attaches_reversal_and_patterns():
    res = timeframe.build_timeframe_result("X", "1d", _bars(_UP + _UP))  # ≥35 bars
    assert res.chart_pattern_analysis is not None
    assert res.reversal_signals is not None
    assert any("pattern=" in e for e in res.timeframe_summary.evidence)


def test_builder_absent_on_insufficient_bars():
    res = timeframe.build_timeframe_result("X", "1d", _bars(_UP[:6]))
    assert res.reversal_signals is None
    assert res.chart_pattern_analysis is None
