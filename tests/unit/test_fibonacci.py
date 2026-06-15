"""Multi-timeframe Fibonacci analysis (F1) — deterministic unit + provider tests.

All bars are synthetic with explicit highs/lows so swings, levels, and zones are
exact. No wall-clock dependence, no network.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.technical import fibonacci as fib
from packages.data.types import FibonacciAnalysis, OHLCVBar


def _series(closes, highs=None, lows=None, tf="1d") -> list[OHLCVBar]:
    highs = highs if highs is not None else list(closes)
    lows = lows if lows is not None else list(closes)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol="X",
            timeframe=tf,
            ts=t0 + timedelta(hours=i),
            open=closes[i],
            high=highs[i],
            low=lows[i],
            close=closes[i],
        )
        for i in range(len(closes))
    ]


def _trend_bars(
    low: float,
    high: float,
    *,
    trend: str,
    last: float,
    plateau: float = 150.0,
    n: int = 130,
    spread: float = 0.01,
    tf: str = "1d",
) -> list[OHLCVBar]:
    """Build n bars on a plateau with one swing low (early/late) and one swing high.

    uptrend: low early (idx 10), high late (idx 120); downtrend: high early, low late.
    """
    closes = [plateau] * n
    closes[-1] = last
    highs = [c * (1 + spread) for c in closes]
    lows = [c * (1 - spread) for c in closes]
    if trend == "up":
        lows[10] = low
        highs[120] = high
    else:
        highs[10] = high
        lows[120] = low
    return _series(closes, highs, lows, tf)


def _level(analysis: FibonacciAnalysis, ratio: float):
    return next((lvl for lvl in analysis.levels if abs(lvl.ratio - ratio) < 1e-6), None)


# ── Levels ───────────────────────────────────────────────────────────────────

def test_uptrend_retracement_levels_correct():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D")
    assert a.validity == "sane"
    assert a.trend_direction == "uptrend"
    assert a.swing_high == 200.0 and a.swing_low == 100.0
    half = _level(a, 0.5)  # uptrend: high - 0.5*range = 200 - 50 = 150
    assert half is not None and abs(half.price - 150.0) < 1e-6
    assert half.kind == "retracement"
    assert half.role == "support"  # 150 < current 160


def test_downtrend_retracement_levels_mirrored():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="down", last=140.0), timeframe="1D")
    assert a.validity == "sane"
    assert a.trend_direction == "downtrend"
    half = _level(a, 0.5)  # downtrend: low + 0.5*range = 100 + 50 = 150
    assert half is not None and abs(half.price - 150.0) < 1e-6
    assert half.role == "resistance"  # 150 > current 140


def test_insufficient_bars_unavailable_with_diagnostic():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0)[:5], timeframe="4H")
    assert a.validity == "unavailable"
    assert any(d.startswith("insufficient_bars") for d in a.diagnostics)
    assert a.levels == []


def test_swing_range_too_small_is_weak_with_no_levels():
    flat = _series([150.0] * 130)  # high=low=close → swing range 0
    a = fib.analyze(flat, timeframe="1D")
    assert a.validity in ("weak", "unavailable")
    assert a.levels == []
    assert any("swing_range_too_small" in d or "invalid_swing" in d for d in a.diagnostics)


def test_missing_or_invalid_price_invents_no_levels():
    assert fib.analyze([], timeframe="1D").levels == []
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=0.0)
    assert a.validity == "unavailable"
    assert a.levels == []


# ── Nearest / zones ──────────────────────────────────────────────────────────

def test_nearest_level_detection():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=151.0)
    assert a.nearest_level is not None
    assert abs(a.nearest_level.ratio - 0.5) < 1e-6  # 150 is closest to 151


def test_near_support_classification():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=150.3)
    assert a.nearest_level.role == "support"
    assert a.zone == "near_support"


def test_near_resistance_classification():
    # current just below the 0.382 retracement (160.8) → that level is resistance.
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=160.6)
    assert a.nearest_level.role == "resistance"
    assert a.zone == "near_resistance"


def test_breakout_classification():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=250.0)
    assert a.zone == "breakout"


def test_breakdown_classification():
    a = fib.analyze(_trend_bars(100.0, 200.0, trend="up", last=160.0), timeframe="1D", current_price=50.0)
    assert a.zone == "breakdown"


# ── Confluence ───────────────────────────────────────────────────────────────

def _analysis(low, high, *, current, tf="1D"):
    return fib.analyze(
        _trend_bars(low, high, trend="up", last=160.0), timeframe=tf, current_price=current
    )


def test_support_confluence_detected():
    f1 = _analysis(100.0, 200.0, current=150.3)        # 0.5 retr = 150 (support)
    f4 = _analysis(100.0, 200.0, current=150.3, tf="4H")
    c = fib.confluence(f1, f4, current_price=150.3, atr_pct=1.0)
    assert c.has_confluence is True
    assert c.confluence_zone == "support"
    assert c.score <= 25


def test_resistance_confluence_detected():
    f1 = _analysis(100.0, 200.0, current=160.6)        # 0.382 retr = 160.8 (resistance)
    f4 = _analysis(100.0, 200.0, current=160.6, tf="4H")
    c = fib.confluence(f1, f4, current_price=160.6, atr_pct=1.0)
    assert c.has_confluence is True
    assert c.confluence_zone == "resistance"


def test_mixed_confluence_detected():
    # 1D level 149.7 (support) vs 4H level 150.3 (resistance), current 150 → straddle.
    f1 = _analysis(99.7, 199.7, current=150.0)   # 0.5 retr = 149.7 (support)
    f4 = _analysis(100.3, 200.3, current=150.0, tf="4H")  # 0.5 retr = 150.3 (resistance)
    c = fib.confluence(f1, f4, current_price=150.0, atr_pct=1.0)
    assert c.has_confluence is True
    assert c.confluence_zone == "mixed"


def test_confluence_with_unavailable_4h_does_not_crash():
    f1 = _analysis(100.0, 200.0, current=150.3)
    f4 = FibonacciAnalysis(timeframe="4H", validity="unavailable", diagnostics=["bars_4h_unavailable"])
    c = fib.confluence(f1, f4, current_price=150.3, atr_pct=1.0)
    assert c.has_confluence is False
    assert c.confluence_zone == "none"


# ── Score ────────────────────────────────────────────────────────────────────

def test_fibonacci_score_never_exceeds_25():
    f1 = _analysis(100.0, 200.0, current=150.3)
    f4 = _analysis(100.0, 200.0, current=150.3, tf="4H")
    c = fib.confluence(f1, f4, current_price=150.3, atr_pct=1.0)
    for momentum in (True, False):
        s = fib.fibonacci_score(f1, f4, c, momentum_ok=momentum)
        assert 0 <= s <= 25
    # unavailable → 0
    none_a = FibonacciAnalysis(timeframe="1D", validity="unavailable")
    assert fib.fibonacci_score(none_a, none_a, None) == 0


# ── Provider integration (get_technical_insight) ─────────────────────────────

def _patch_bars(monkeypatch, *, bars_1d, bars_4h):
    def fake_get_bars(symbol, timeframe="1d"):
        return bars_1d if timeframe == "1d" else (bars_4h if timeframe == "4h" else [])

    monkeypatch.setattr("packages.data.providers.ohlcv.get_bars", fake_get_bars)


def test_technical_insight_contains_all_fib_fields(monkeypatch):
    from packages.data.providers import technical as tp

    up1d = _trend_bars(100.0, 200.0, trend="up", last=160.0, tf="1d")
    up4h = _trend_bars(100.0, 200.0, trend="up", last=160.0, tf="4h")
    _patch_bars(monkeypatch, bars_1d=up1d, bars_4h=up4h)

    insight = tp.get_technical_insight("BTCUSD")
    assert insight.symbol == "BTCUSD"
    assert insight.fib_1d is not None and insight.fib_1d.validity == "sane"
    assert insight.fib_4h is not None and insight.fib_4h.validity == "sane"
    assert insight.fib_confluence is not None
    assert 0 <= insight.fibonacci_score <= 25
    # fibonacci_score is a SEPARATE field — not the per-TF technical score.
    assert not hasattr(insight, "technical_score")
    assert not hasattr(insight, "score")


def test_4h_unavailable_keeps_1d_and_does_not_crash(monkeypatch):
    from packages.data.providers import technical as tp

    up1d = _trend_bars(100.0, 200.0, trend="up", last=160.0, tf="1d")
    _patch_bars(monkeypatch, bars_1d=up1d, bars_4h=[])

    insight = tp.get_technical_insight("BTCUSD")
    assert insight.fib_1d.validity == "sane"            # 1D kept
    assert insight.fib_4h.validity == "unavailable"     # 4H marked, not invented
    assert insight.fib_4h.levels == []
    assert insight.fib_confluence.has_confluence is False


def test_fibonacci_does_not_change_technical_score(monkeypatch):
    from packages.data.providers import technical as tp

    up1d = _trend_bars(100.0, 200.0, trend="up", last=160.0, tf="1d")
    up4h = _trend_bars(100.0, 200.0, trend="up", last=160.0, tf="4h")
    _patch_bars(monkeypatch, bars_1d=up1d, bars_4h=up4h)

    before = tp.get_snapshot("BTCUSD", "1d").score
    tp.get_technical_insight("BTCUSD")            # compute fib evidence
    after = tp.get_snapshot("BTCUSD", "1d").score
    assert before == after                        # technical_score untouched
