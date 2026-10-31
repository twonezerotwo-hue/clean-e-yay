"""Maliyet modeli: EV'deki maliyet (R) = varlığın gidiş-dönüş maliyeti / açılış stop mesafesi."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.decision import engine as dec

CFG = {"cost_r": 0.1, "round_trip_cost_pct": {"default": 0.08, "BTCUSD": 0.22, "XLE": 0.04}}


def _snap(symbol, price):
    return SimpleNamespace(prices=[SimpleNamespace(symbol=symbol, price=price)],
                           technicals_by_tf={symbol: {"1h": SimpleNamespace(atr=1.0)}})


def test_cost_r_is_cost_over_stop_distance(monkeypatch):
    # stop %1 uzakta → BTC %0,22 / %1 = 0,22R; ETF %0,04 / %1 = 0,04R
    monkeypatch.setattr("packages.paper.lifecycle.canonical_targets",
                        lambda symbol, side, price, tf, atr: SimpleNamespace(sl=price * 0.99))
    assert dec._cost_r("BTCUSD", "long", _snap("BTCUSD", 100.0), "1h", CFG) == pytest.approx(0.22)
    assert dec._cost_r("XLE", "long", _snap("XLE", 100.0), "1h", CFG) == pytest.approx(0.04)
    assert dec._cost_r("COPPER", "short", _snap("COPPER", 100.0), "1h", CFG) == pytest.approx(0.08)


def test_cost_r_falls_back_without_price_table_or_stop(monkeypatch):
    monkeypatch.setattr("packages.paper.lifecycle.canonical_targets",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no targets")))
    assert dec._cost_r("BTCUSD", "long", _snap("BTCUSD", 100.0), "1h", CFG) == 0.1
    assert dec._cost_r("BTCUSD", "long", _snap("ETHUSD", 100.0), "1h", CFG) == 0.1   # fiyat yok
    assert dec._cost_r("BTCUSD", "long", _snap("BTCUSD", 100.0), "1h", {"cost_r": 0.1}) == 0.1
