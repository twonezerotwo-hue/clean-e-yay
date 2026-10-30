"""Tek makro sürpriz tablosu: owner tablosunun yönleri, nedensellikte varlık başına katkı."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.causal.engine import build_shadow
from packages.data.types import Catalyst
from packages.macro import matrix
from packages.macro.evidence import build_macro_evidence
from packages.world_state.engine import build


def _sign(topic: str, symbol: str, cls: str | None = None, positive: bool = True) -> int:
    w = matrix.weight(topic, symbol, cls) * (1 if positive else -1)
    return 1 if w > 0 else -1 if w < 0 else 0


@pytest.mark.parametrize(("topic", "positive", "expected"), [
    ("cpi", True, {"XAUUSD": -1, "BTCUSD": -1, "DXY": 1, "US10Y": 1}),
    ("cpi", False, {"XAUUSD": 1, "BTCUSD": 1, "DXY": -1}),
    ("nfp", True, {"XAUUSD": -1, "BTCUSD": 0, "WTI": 1}),
    ("fed_policy", True, {"XAUUSD": -1, "XAGUSD": -1, "BTCUSD": -1, "XLK": -1}),
    ("fed_policy", False, {"XAUUSD": 1, "XAGUSD": 1, "BTCUSD": 1}),
    ("ism_pmi", True, {"XAGUSD": 1, "COPPER": 1, "XAUUSD": 0}),
    ("gdp", False, {"WTI": -1, "XLK": -1}),
])
def test_owner_table_directions(topic, positive, expected):
    t = matrix.topic_for(topic)
    classes = {"BTCUSD": "crypto"}
    for symbol, want in expected.items():
        assert _sign(t, symbol, classes.get(symbol), positive) == want, (topic, symbol)


def test_raw_surprise_flip_for_unemployment_and_oil_stocks():
    # İşsizlik beklentiden yüksek → ham +, normalleştirilmiş − (zayıf ekonomi) → petrol ↓.
    assert matrix.raw_sign("unemployment") == -1 and matrix.raw_sign("oil_inventory") == -1
    assert matrix.raw_sign("inflation") == 1
    assert 1 * matrix.raw_sign("oil_inventory") * matrix.weight("oil_inventory", "WTI") < 0  # stok yüksek → petrol ↓
    assert matrix.weight("natural_gas_storage", "NATGAS") < 0  # gaz stoku yüksek → doğal gaz ↓


def test_event_outcome_expectations_come_from_table():
    weak_jobs = matrix.expected_signs(matrix.topic_for("jobs"), positive=False)
    assert weak_jobs["XAUUSD"] == 1 and weak_jobs["DXY"] == -1 and "BTCUSD" not in weak_jobs
    hawkish = matrix.expected_signs(matrix.topic_for("central_bank"), positive=True)
    assert hawkish["XAUUSD"] == -1 and hawkish["VIX"] == 1


def _snapshot(**kwargs):
    rotation = SimpleNamespace(status="OK", per_symbol={"DXY": 70.0, "SP500": 65.0, "BTCUSD": 60.0, "XAUUSD": 58.0},
                               evidence=["rotation fixture"])
    values = {"generated_at": datetime.now(UTC), "rotation": rotation, "quality": SimpleNamespace(status="OK", score=90.0),
              "headlines": [], "catalysts": [], "catalyst_impacts": []}
    values.update(kwargs)
    return SimpleNamespace(**values)


def _hot_cpi() -> Catalyst:
    return Catalyst(id="cpi-1", ts=datetime.now(UTC) - timedelta(minutes=20), title="US CPI", source="calendar", verified=True,
                    actual=3.4, expected=3.0, historical_surprise_volatility=0.2)


def _gold(world):
    return next(i for i in build_shadow(world, ["XAUUSD", "BTCUSD"]).impacts if i.symbol == "XAUUSD")


def _baseline(monkeypatch):
    from packages.data import snapshot_store
    from packages.macro import confirm

    confirm.reset_cache()
    doc = {"data_snapshot": {"prices": [{"symbol": "DXY", "price": 100.0}, {"symbol": "XAUUSD", "price": 2000.0},
                                        {"symbol": "BTCUSD", "price": 80000.0}]}}
    monkeypatch.setattr(snapshot_store, "nearest", lambda target, side, max_gap_seconds: doc)


CONFIRMING = {"DXY": 100.3, "XAUUSD": 1985.0, "BTCUSD": 79000.0}


def test_hot_cpi_turns_gold_and_btc_down(monkeypatch):
    _baseline(monkeypatch)
    calm = build(_snapshot())
    hot = build(_snapshot(catalysts=[_hot_cpi()]))
    assert hot.inflation_pressure == calm.inflation_pressure  # faktöre karışmaz
    impacts = {i.symbol: i for i in build_shadow(hot, ["XAUUSD", "BTCUSD"], prices=CONFIRMING).impacts}
    calm_impacts = {i.symbol: i for i in build_shadow(calm, ["XAUUSD", "BTCUSD"], prices=CONFIRMING).impacts}
    for symbol in ("XAUUSD", "BTCUSD"):
        assert impacts[symbol].macro_surprise_contribution < 0
        if calm_impacts[symbol].base_thesis_score is not None:
            assert impacts[symbol].base_thesis_score < calm_impacts[symbol].base_thesis_score


def test_unconfirmed_surprise_adds_nothing(monkeypatch):
    _baseline(monkeypatch)
    hot = build(_snapshot(catalysts=[_hot_cpi()]))
    against = {"DXY": 100.3, "XAUUSD": 2015.0, "BTCUSD": 79000.0}  # altın sıcak CPI'ya rağmen yükseldi
    gold = next(i for i in build_shadow(hot, ["XAUUSD"], prices=against).impacts if i.symbol == "XAUUSD")
    assert gold.macro_surprise_contribution == 0.0
    assert any(d.endswith(":CONTRADICTED") for d in gold.drivers)


def test_shadow_evidence_reads_table_for_hot_cpi():
    rows = build_macro_evidence(_snapshot(catalysts=[_hot_cpi()]))
    by_asset = {r["asset"]: r["direction"] for r in rows}
    assert by_asset.get("XAUUSD") == "bearish"  # eski kod: bullish
    assert by_asset.get("DXY") == "bullish"     # eski kod: bearish
