"""Zone artifact yaş kontrolü (denetim bulgusu: karar/skor bayat bölge okumasın).

- `load_fresh`: generated_at ≤ max_age → artifact; bayat/yok/bozuk → None.
- `fresh_zones_by_symbol`: taze → {sembol: zones}; bayat → {}.
- Görüntü tüketicisi `_load` yaş-kontrolsüz kalır (stale gösterip uyarabilsin).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.learning import zone_proposer as zp


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    p = tmp_path / "zone_proposer.json"
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(p))

    def _write(age_sec: float, assets=None):
        gen = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
        p.write_text(json.dumps({
            "engine": zp._ENGINE, "generated_at": gen,
            "assets": assets if assets is not None else [
                {"symbol": "BTCUSD", "status": "OK",
                 "zones": [{"low": 100.0, "high": 110.0}]},
            ],
        }), encoding="utf-8")

    return _write


def test_fresh_artifact_returned(artifact):
    artifact(age_sec=3600)  # 1 saat
    assert zp.load_fresh() is not None
    zs = zp.fresh_zones_by_symbol()
    assert zs["BTCUSD"] == [{"low": 100.0, "high": 110.0}]


def test_stale_artifact_is_none(artifact):
    artifact(age_sec=3 * 86400)  # 3 gün > 2 gün tavan
    assert zp.load_fresh() is None
    assert zp.fresh_zones_by_symbol() == {}


def test_missing_artifact_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(tmp_path / "yok.json"))
    assert zp.load_fresh() is None
    assert zp.fresh_zones_by_symbol() == {}


def test_corrupt_generated_at_is_none(artifact, tmp_path, monkeypatch):
    p = tmp_path / "zone_proposer.json"
    monkeypatch.setenv("ZONE_PROPOSER_PATH", str(p))
    p.write_text(json.dumps({"engine": zp._ENGINE, "generated_at": "bozuk",
                             "assets": []}), encoding="utf-8")
    assert zp.load_fresh() is None  # parse edilemeyen tarih → bayat say (uydurma yok)


def test_display_load_ignores_age(artifact):
    """Görüntü yolu (_load) bayat artifact'ı yine döndürür (uyarıyla gösterebilsin)."""
    artifact(age_sec=5 * 86400)
    assert zp._load() is not None  # _load yaş-kontrolsüz (viewmodel için)
    assert zp.load_fresh() is None  # karar yolu bayatı reddeder
