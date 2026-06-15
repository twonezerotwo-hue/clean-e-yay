"""Pure indicator unit tests (T1) — adx/DI, atr_percent, swing pivots, vwap, bb.

Deterministic synthetic bars with explicit highs/lows; no wall-clock, no network.
Every indicator must return None on insufficient history (DATA_POLICY) — never a
fabricated value.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.technical import indicators as ind
from packages.data.types import OHLCVBar


def _bars(rows, *, tf="1h", vol=None) -> list[OHLCVBar]:
    """rows: list of (high, low, close). open=close; volume optional."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    out: list[OHLCVBar] = []
    for i, (h, lo, c) in enumerate(rows):
        out.append(
            OHLCVBar(
                symbol="X",
                timeframe=tf,
                ts=t0 + timedelta(hours=i),
                open=c,
                high=h,
                low=lo,
                close=c,
                volume=(vol[i] if vol is not None else None),
            )
        )
    return out


def _trend(n: int, *, step: float, start: float = 100.0) -> list[OHLCVBar]:
    """Monotonic series; step>0 = up, step<0 = down. high=close+0.5, low=close-0.5."""
    rows = []
    for i in range(n):
        c = start + step * i
        rows.append((c + 0.5, c - 0.5, c))
    return _bars(rows)


# ── ATR% ─────────────────────────────────────────────────────────────────────

def test_atr_percent_relative_to_price():
    bars = _trend(30, step=0.0)  # flat closes → TR from the 1.0-wide candles
    a = ind.atr(bars)
    p = ind.atr_percent(bars)
    assert a is not None and p is not None
    assert abs(p - a / bars[-1].close * 100.0) < 1e-9


def test_atr_percent_none_on_insufficient():
    assert ind.atr_percent(_trend(5, step=1.0)) is None


# ── ADX / DI ───────────────────────────────────────────────────────────────--

def test_adx_strong_uptrend_high_with_plus_di_dominant():
    adx, plus_di, minus_di = ind.adx(_trend(60, step=1.0))
    assert adx > 40.0            # monotonic trend → strong ADX
    assert plus_di > minus_di    # direction up
    assert minus_di < 1.0


def test_adx_strong_downtrend_minus_di_dominant():
    adx, plus_di, minus_di = ind.adx(_trend(60, step=-1.0))
    assert adx > 40.0
    assert minus_di > plus_di


def test_adx_flat_market_is_zero():
    # No range, no movement → no directional signal.
    adx, plus_di, minus_di = ind.adx(_bars([(100.0, 100.0, 100.0)] * 60))
    assert adx == 0.0
    assert plus_di == 0.0 and minus_di == 0.0


def test_adx_none_on_insufficient():
    assert ind.adx(_trend(20, step=1.0)) is None  # needs >= 2*period+1 = 29


# ── Swing pivots ──────────────────────────────────────────────────────────────

def test_swing_pivots_detects_single_high_and_low():
    highs = [5, 6, 7, 8, 9, 8, 7, 6, 5]
    lows = [5, 4, 3, 2, 1, 2, 3, 4, 5]
    bars = _bars([(h, lo, (h + lo) / 2) for h, lo in zip(highs, lows, strict=True)])
    sh, sl = ind.swing_pivots(bars, left=2, right=2)
    assert sh == [9.0]
    assert sl == [1.0]


def test_swing_pivots_none_on_insufficient():
    assert ind.swing_pivots(_trend(3, step=1.0), left=2, right=2) is None


def test_swing_pivots_empty_when_no_pivot():
    sh, sl = ind.swing_pivots(_trend(10, step=1.0), left=2, right=2)  # monotonic → no interior pivot
    assert sh == [] and sl == []


# ── VWAP ───────────────────────────────────────────────────────────────────--

def test_vwap_volume_weighted():
    bars = _bars(
        [(12, 8, 10), (14, 10, 12), (11, 9, 10)],
        vol=[10.0, 20.0, 30.0],
    )
    # typicals: 10, 12, 10 → (10*10 + 12*20 + 10*30) / 60 = 640/60
    v = ind.vwap(bars)
    assert v is not None and abs(v - 640.0 / 60.0) < 1e-9


def test_vwap_none_without_volume():
    bars = _bars([(12, 8, 10), (14, 10, 12)])  # volume=None
    assert ind.vwap(bars) is None


# ── Bollinger width ───────────────────────────────────────────────────────────

def test_bollinger_width_zero_when_flat():
    assert ind.bollinger_width([100.0] * 20) == 0.0


def test_bollinger_width_positive_when_volatile():
    closes = [100.0 + (5.0 if i % 2 else -5.0) for i in range(20)]
    w = ind.bollinger_width(closes)
    assert w is not None and w > 0.0


def test_bollinger_width_none_on_insufficient():
    assert ind.bollinger_width([100.0] * 10) is None
