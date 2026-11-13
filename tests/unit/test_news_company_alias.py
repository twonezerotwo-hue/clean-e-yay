"""Şirket adıyla anılan haber kayıtlı sembole bağlanır (13 Kasım 2026: Nvidia başlıklarının %3'ü NVDA'daydı)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.data.providers.news.classify import classify_asset_impact

ASSETS = [
    SimpleNamespace(symbol="NVDA", label="nvda", asset_class="risk"),
    SimpleNamespace(symbol="XLE", label="Enerji Sektörü", asset_class="equity"),
    SimpleNamespace(symbol="XLK", label="Teknoloji Sektörü", asset_class="equity"),
    SimpleNamespace(symbol="XLV", label="Sağlık Sektörü", asset_class="equity"),
    SimpleNamespace(symbol="XLP", label="Temel Tüketim", asset_class="equity"),
]


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr("packages.data.registry.assets.all_assets", lambda: list(ASSETS))


def test_company_name_and_ceo_map_to_registered_ticker(registry) -> None:
    assert classify_asset_impact("Nvidia board weighs ouster of CEO", "bearish").get("NVDA") == -1.0
    assert classify_asset_impact("Jensen Huang steps down after board probe", "bearish").get("NVDA") == -1.0


def test_named_company_survives_the_four_impact_cap(registry) -> None:
    impacts = classify_asset_impact("US Equity Indexes Mixed After Nvidia CEO Resigns, Treasury Yields Soar", "bearish")
    assert "NVDA" in impacts and len(impacts) <= 4
    assert next(iter(k for k in impacts if k in {a.symbol for a in ASSETS})) == "NVDA"


def test_alias_never_invents_an_unregistered_symbol(monkeypatch) -> None:
    monkeypatch.setattr("packages.data.registry.assets.all_assets", lambda: [ASSETS[1]])
    assert "NVDA" not in classify_asset_impact("Nvidia shares slide", "bearish")


def test_surname_alone_is_not_enough(registry) -> None:
    assert "NVDA" not in classify_asset_impact("Huang family opens new restaurant", "neutral")
