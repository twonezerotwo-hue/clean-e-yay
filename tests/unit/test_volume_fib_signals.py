"""Hacim itkisi, OBV eğilimi, Fibonacci geri çekilme: saf ölçüm sinyalleri, canlıya bağlı değil."""
from __future__ import annotations

from types import SimpleNamespace

from packages.signals import fib_retracement, obv_trend, volume_thrust


def _bar(close, volume=100.0, high=None, low=None):
    return SimpleNamespace(close=close, open=close, high=high if high is not None else close + 0.5,
                           low=low if low is not None else close - 0.5, volume=volume)


def test_volume_thrust_direction_and_missing_volume():
    flat = [_bar(100.0) for _ in range(21)]
    assert volume_thrust.lean([*flat, _bar(101.0, volume=200.0)]) == 1.0
    assert volume_thrust.lean([*flat, _bar(99.0, volume=200.0)]) == -1.0
    assert volume_thrust.lean([*flat, _bar(101.0, volume=120.0)]) == 0.0
    assert volume_thrust.lean([_bar(100.0, volume=None) for _ in range(22)]) is None
    assert volume_thrust.lean(flat[:5]) is None


def test_obv_trend_accumulation_and_distribution():
    up = [_bar(100.0 + i) for i in range(21)]
    down = [_bar(100.0 - i) for i in range(21)]
    assert obv_trend.lean(up) == 1.0
    assert obv_trend.lean(down) == -1.0
    assert obv_trend.lean([_bar(100.0 + (i % 2)) for i in range(21)]) == 0.0
    assert obv_trend.lean([*up[:-1], _bar(130.0, volume=None)]) is None


def test_fib_retracement_zone():
    rise = [_bar(100.0 + i, high=100.0 + i, low=100.0 + i) for i in range(41)]          # 100 → 140
    pullback = [_bar(140.0 - i, high=140.0 - i, low=140.0 - i) for i in range(1, 20)]   # 139 → 121
    into_zone = [*rise, *pullback, _bar(113.0, high=113.0, low=113.0)][-60:]          # %67,5 geri çekilme
    assert fib_retracement.lean(into_zone) == 1.0
    base = [_bar(100.0, high=100.0, low=100.0) for _ in range(20)]
    assert fib_retracement.lean([*base, *rise, _bar(135.0, high=135.0, low=135.0)]) == 0.0  # sığ geri çekilme
    fall = [_bar(140.0 - i, high=140.0 - i, low=140.0 - i) for i in range(41)]               # 140 → 100
    bounce = [_bar(127.0, high=127.0, low=127.0)]                                           # %67,5 tepki
    top = [_bar(140.0, high=140.0, low=140.0) for _ in range(20)]
    assert fib_retracement.lean([*top, *fall, *bounce]) == -1.0
    assert fib_retracement.lean(rise[:10]) is None


def test_new_signals_are_not_in_live_lean_set():
    """Canlı giriş kalitesi `collect_leans` kümesini kullanır; yeni sinyaller karne geçmeden girmez."""
    from datetime import UTC, datetime, timedelta

    from packages.data.types import OHLCVBar
    from packages.scoring import tf_scoring_v2

    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    bars = [OHLCVBar(symbol="BTCUSD", timeframe="1h", ts=t0 + timedelta(hours=i), open=100.0 + (i % 7),
                     high=101.0 + (i % 7), low=99.0 + (i % 7), close=100.0 + (i % 7), volume=100.0 + i,
                     source="fixture", verified=True) for i in range(260)]
    leans = tf_scoring_v2.collect_leans("1h", bars)
    assert not {"volume_thrust", "obv_trend", "fib_retracement"} & set(leans)
