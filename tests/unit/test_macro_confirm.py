"""Açıklama sonrası çapraz teyit: bekleme, teyit, çelişki, dönüş, zayıf hareket."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.macro import confirm

REL = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)
BASE = {"DXY": 100.0, "XAUUSD": 2000.0, "BTCUSD": 80000.0}


@pytest.fixture(autouse=True)
def _store(monkeypatch):
    from packages.data import snapshot_store

    confirm.reset_cache()
    doc = {"data_snapshot": {"prices": [{"symbol": s, "price": p} for s, p in BASE.items()]}}
    monkeypatch.setattr(snapshot_store, "nearest", lambda target, side, max_gap_seconds: doc)
    yield
    confirm.reset_cache()


def _assess(prices, *, minutes=20, symbol="XAUUSD", normalized=0.5, topic="inflation", asset_class="precious_metal"):
    return confirm.assess(event_id="cpi", topic=topic, normalized=normalized, released_at=REL, symbol=symbol,
                          asset_class=asset_class, prices_now=prices, now=REL + timedelta(minutes=minutes))


def test_pending_before_window():
    assert _assess({"DXY": 100.5, "XAUUSD": 1980.0}, minutes=5) == (0.0, "PENDING")


def test_hot_cpi_confirmed_when_dollar_up_and_gold_down():
    assert _assess({"DXY": 100.3, "XAUUSD": 1985.0}) == (1.0, "CONFIRMED")


def test_contradicted_when_gold_rises_or_reaction_reverses():
    assert _assess({"DXY": 100.3, "XAUUSD": 2010.0}) == (0.0, "CONTRADICTED")
    assert _assess({"DXY": 99.7, "XAUUSD": 1985.0}, minutes=60) == (0.0, "CONTRADICTED")  # dolar döndü


def test_weak_move_and_missing_baseline(monkeypatch):
    from packages.data import snapshot_store

    assert _assess({"DXY": 100.01, "XAUUSD": 1999.9}) == (0.5, "WEAK")
    confirm.reset_cache()
    monkeypatch.setattr(snapshot_store, "nearest", lambda target, side, max_gap_seconds: None)
    assert _assess({"DXY": 100.3, "XAUUSD": 1985.0}) == (0.0, "UNAVAILABLE")


def test_cool_cpi_flips_expected_direction_and_quotes_accepted():
    quote = type("Q", (), {})
    dxy, gold = quote(), quote()
    dxy.symbol, dxy.price, gold.symbol, gold.price = "DXY", 99.7, "XAUUSD", 2015.0
    assert _assess({"DXY": dxy, "XAUUSD": gold}, normalized=-0.5) == (1.0, "CONFIRMED")


def test_asset_without_direction_contributes_nothing():
    assert _assess({"DXY": 100.3, "BTCUSD": 79000.0}, symbol="BTCUSD", topic="jobs", asset_class="crypto")[1] == "NO_DIRECTION"
