"""B4 — backtest çıkışı canlı stop kuralıyla aynı (execution_sim.bar_exit)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data import strategy_backtest
from packages.paper import execution_sim as ex


def _bx(**kw):
    base = dict(side="long", entry_price=100.0, sl=95.0, tp=110.0, close_based=True, disaster_mult=2.0)
    base.update(kw)
    return ex.bar_exit(**base)


def test_disaster_level_matches_formula():
    assert ex.disaster_level("long", 100.0, 95.0, 2.0) == 90.0
    assert ex.disaster_level("short", 100.0, 105.0, 2.0) == 110.0
    assert ex.disaster_level("long", None, 95.0, 2.0) is None


def test_wick_below_sl_but_close_above_is_not_a_stop():
    # Fitil SL altına sarktı ama kapanış üstünde → canlıda stop yok.
    assert _bx(high=101, low=94, close=97) is None


def test_close_below_sl_exits_at_close():
    assert _bx(high=99, low=93, close=94) == (ex.SL_HIT, 94)


def test_disaster_wick_exits_at_level():
    assert _bx(high=99, low=89, close=96) == (ex.SL_HIT, 90.0)


def test_tp_wick_before_close_stop():
    # TP fitille vurulur (bar kapanmadan) — kapanış stopundan önce.
    assert _bx(high=111, low=93, close=94) == (ex.TP_HIT, 110.0)


def test_short_side_mirrors():
    r = ex.bar_exit(side="short", entry_price=100.0, sl=105.0, tp=90.0,
                    high=106, low=99, close=104, close_based=True)
    assert r is None
    r = ex.bar_exit(side="short", entry_price=100.0, sl=105.0, tp=90.0,
                    high=106, low=99, close=105.5, close_based=True)
    assert r == (ex.SL_HIT, 105.5)


def test_wick_mode_when_close_based_off():
    assert _bx(close_based=False, high=101, low=94, close=97) == (ex.SL_HIT, 95.0)
    assert _bx(close_based=False, high=111, low=94, close=97) == (ex.SL_HIT, 95.0)


def test_strategy_backtest_uses_live_exit_policy(monkeypatch):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    n = strategy_backtest._WARMUP_BARS
    bars = [SimpleNamespace(ts=t0 + timedelta(days=i), open=100, high=100, low=100, close=100)
            for i in range(n + 1)]
    # giriş barı (close=100) → sonraki bar fitille SL altına iner ama yukarıda kapanır
    bars.append(SimpleNamespace(ts=t0 + timedelta(days=n + 1), open=100, high=100.5, low=99.2, close=99.8))
    bars += [SimpleNamespace(ts=t0 + timedelta(days=n + 2 + k), open=100, high=100.2, low=99.9, close=100)
             for k in range(5)]
    monkeypatch.setattr(strategy_backtest, "get_bars", lambda s, tf: bars)
    calls = {"n": 0}

    def fake_tf(symbol, tf, window):
        calls["n"] += 1
        bias = "BULLISH" if calls["n"] == 1 else "NEUTRAL"
        return SimpleNamespace(timeframe_summary=SimpleNamespace(bias=bias))

    monkeypatch.setattr(strategy_backtest, "build_timeframe_result", fake_tf)
    monkeypatch.setattr(strategy_backtest, "_sl_tp_pct", lambda s: (0.005, 0.01))

    monkeypatch.setattr(strategy_backtest, "_exit_policy", lambda: (True, 2.0))
    live = strategy_backtest.run_signal_backtest("BTCUSD", "1d")
    assert live["total_trades"] == 0, "kapanış stopu: fitil tek başına stop değil"

    calls["n"] = 0
    monkeypatch.setattr(strategy_backtest, "_exit_policy", lambda: (False, 2.0))
    wick = strategy_backtest.run_signal_backtest("BTCUSD", "1d")
    assert wick["total_trades"] == 1 and wick["trades"][0]["exit_reason"] == ex.SL_HIT


@pytest.mark.parametrize("enabled", [True, False])
def test_exit_policy_reads_config(monkeypatch, enabled):
    monkeypatch.setattr(strategy_backtest, "load_thresholds",
                        lambda: {"exit_close_based_stop": {"enabled": enabled, "disaster_mult": 3}})
    assert strategy_backtest._exit_policy() == (enabled, 3.0)
