"""Performans kanıtı: en büyük düşüş (R), maliyet sonrası net getiri ve al-tut kıyası."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.data.types import OHLCVBar
from packages.learning import benchmark

T0 = datetime(2026, 6, 1, tzinfo=UTC)


def _o(r, pnl, opened, closed, symbol="BTCUSD"):
    return SimpleNamespace(r_multiple=r, pnl=pnl, symbol=symbol,
                           opened_at=opened.isoformat(), closed_at=closed.isoformat())


def test_max_drawdown_follows_close_order():
    rows = [_o(1.0, 100, T0, T0 + timedelta(days=1)), _o(-2.0, -200, T0, T0 + timedelta(days=2)),
            _o(-1.0, -100, T0, T0 + timedelta(days=3)), _o(3.0, 300, T0, T0 + timedelta(days=4))]
    assert benchmark.max_drawdown_r(rows) == -3.0
    assert benchmark.max_drawdown_r([]) is None


def test_buy_and_hold_uses_disk_prices_and_costs(monkeypatch):
    from packages.data.providers.ohlcv import cache
    bars = [OHLCVBar(symbol="BTCUSD", timeframe="1d", ts=T0 + timedelta(days=i), open=100 + i,
                     high=100 + i, low=100 + i, close=100.0 + i, volume=1.0) for i in range(11)]
    monkeypatch.setattr(cache, "load", lambda s, tf: SimpleNamespace(bars=bars))
    monkeypatch.setattr(benchmark, "cost_r", lambda: 0.1)
    rows = [_o(1.0, 500.0, T0, T0 + timedelta(days=10))]       # risk 500$ → maliyet 50$
    out = benchmark.buy_and_hold(rows, 100_000.0)
    assert out["benchmark_return_pct"] == 10.0                 # 100 → 110
    assert out["system_net_return_pct"] == 0.45                # (500 − 50) / 100k
    monkeypatch.setattr(cache, "load", lambda s, tf: None)
    assert benchmark.buy_and_hold(rows, 100_000.0) is None     # fiyat yok → uydurma yok
