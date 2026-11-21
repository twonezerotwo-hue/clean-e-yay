"""Özel varlık dosyası: atomik yazım, bozuk dosyada veri kaybı yok, önbellekli okuma."""
from __future__ import annotations

import json

import pytest

from packages.data.registry import custom_assets as ca


@pytest.fixture
def path(tmp_path, monkeypatch):
    p = tmp_path / "custom_assets.json"
    monkeypatch.setenv("CUSTOM_ASSETS_PATH", str(p))
    ca._CACHE["key"] = None
    return p


def _asset(sym: str) -> ca.CustomAsset:
    return ca.CustomAsset(symbol=sym, label=sym, provider="yfinance", ticker=sym)


def test_add_remove_roundtrip(path):
    ca.add(_asset("NVDA"))
    ca.add(_asset("AMD"))
    assert [a.symbol for a in ca.all_custom()] == ["NVDA", "AMD"]
    assert ca.remove("NVDA") is True
    assert [a.symbol for a in ca.all_custom()] == ["AMD"]
    assert json.loads(path.read_text(encoding="utf-8")).keys() == {"AMD"}
    assert [f.name for f in path.parent.iterdir()] == ["custom_assets.json"]


def test_corrupt_file_is_never_overwritten(path):
    # Eski kod: bozuk dosya boş okunur, sonraki ekleme bütün özel varlıkları siler.
    broken = '{"NVDA": {"ticker": "NVDA"}, "AMD": '
    path.write_text(broken, encoding="utf-8")
    assert ca.all_custom() == []
    with pytest.raises(ca.CorruptCustomAssets):
        ca.add(_asset("TSLA"))
    with pytest.raises(ca.CorruptCustomAssets):
        ca.remove("NVDA")
    assert path.read_text(encoding="utf-8") == broken


def test_reads_are_cached_until_file_changes(path, monkeypatch):
    ca.add(_asset("NVDA"))
    assert ca.get("NVDA") is not None
    calls = {"n": 0}
    real = ca._parse

    def counting(p):
        calls["n"] += 1
        return real(p)

    monkeypatch.setattr(ca, "_parse", counting)
    for _ in range(5):
        assert "NVDA" in {a.symbol for a in ca.all_custom()}
    assert calls["n"] == 0
    ca.add(_asset("AMD"))
    assert {a.symbol for a in ca.all_custom()} == {"NVDA", "AMD"}
