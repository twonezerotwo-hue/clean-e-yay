"""Teknik oy KADEMESİ testleri — touche = v4 → backup → zemin (2026-07-12).

- `_touche_shadow`: üretici artifact'ından (v4, backup) çifti → 0-100 mapping;
  eksik/bayat/yönsüz → (None, None).
- Flag KAPALI: canlı teknik oy zemin motor (bayt-aynı); varyantlar yalnız gözlem.
- Flag AÇIK: v4 varsa v4; v4 çekimserse backup; ikisi de yoksa zemin (dürüst).
- RiskGate/boyut/manuel kuyruk bu kademeden ETKİLENMEZ (yalnız yön oyu).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override

_FLAG_ON = {"consensus": {"touche_v4": True}}
_FLAG_OFF = {"consensus": {"touche_v4": False}}


def _write_artifact(path, per_symbol: dict, *, age_sec: float = 0.0) -> None:
    gen = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
    path.write_text(
        json.dumps({"generated_at": gen, "per_symbol": per_symbol}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """Üretici artifact'ını tmp yola yönlendir; yazıcı fonksiyonu döndür."""
    p = tmp_path / "tf_scoring_v2_shadow.json"
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(p))
    return lambda per_symbol, **kw: _write_artifact(p, per_symbol, **kw)


# ── _touche_shadow birim (okuma + mapping) ───────────────────────────────────

def test_shadow_maps_directions_to_0_100(artifact):
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": -0.6}})
    v4, bak = ce._touche_shadow("BTCUSD")
    assert v4 == pytest.approx(70.0)   # 50 + 0.4*50
    assert bak == pytest.approx(20.0)  # 50 - 30


def test_shadow_missing_artifact_is_none_pair(monkeypatch, tmp_path):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))
    assert ce._touche_shadow("BTCUSD") == (None, None)


def test_shadow_stale_artifact_falls_back(artifact):
    # Öğrenme worker'ı durmuş → 3h+ bayat artifact → (None, None) → zemine düş.
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2}}, age_sec=4 * 3600)
    assert ce._touche_shadow("BTCUSD") == (None, None)


def test_shadow_partial_directions(artifact):
    artifact({"BTCUSD": {"direction_v4": None, "direction_backup": 0.2}})
    v4, bak = ce._touche_shadow("BTCUSD")
    assert v4 is None and bak == pytest.approx(60.0)
    artifact({"ETHUSD": {"direction_v4": 0.5}})  # başka sembol
    assert ce._touche_shadow("BTCUSD") == (None, None)


def test_shadow_clamps(artifact):
    artifact({"BTCUSD": {"direction_v4": 5.0, "direction_backup": -5.0}})
    v4, bak = ce._touche_shadow("BTCUSD")
    assert v4 == pytest.approx(100.0) and bak == pytest.approx(0.0)


# ── build() kablolama (canlı 5-modül consensus) ──────────────────────────────

def _snap(direction_score: float = 60.0):
    tech = SimpleNamespace(direction_score=direction_score, status="OK", timeframe="4h", score=direction_score)
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"4h": tech}},
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status="OK"),
        volatility={},
        derivatives={},
        options={},
    )


def _regime():
    from packages.regime.classifier import RegimeLayer, RegimeOutput
    return RegimeOutput(
        label="NEUTRAL",
        layers=[RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
                RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[])],
    )


def test_flag_off_live_touche_is_base_with_observe_line(artifact):
    # Flag AKTİF default (canlı config touche_v4=true) → test flag'i explicit KAPATIR.
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": 0.2}})
    with threshold_override(_FLAG_OFF):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)  # zemin (flag kapalı → eski davranış)
    assert any(w == "touche_observe:base=60.0:backup=60.0:v4=70.0:used=base" for w in res.warnings)


def test_flag_on_v4_speaks_first(artifact):
    artifact({"BTCUSD": {"direction_v4": 0.4, "direction_backup": -0.6}})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(70.0)  # v4 CANLI (backup okunmaz)
    assert any(w == "touche_observe:base=60.0:backup=20.0:v4=70.0:used=v4" for w in res.warnings)


def test_flag_on_v4_silent_backup_speaks(artifact):
    artifact({"BTCUSD": {"direction_v4": None, "direction_backup": -0.6}})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(20.0)  # backup konuştu
    assert any(w == "touche_observe:base=60.0:backup=20.0:v4=none:used=backup" for w in res.warnings)


def test_flag_on_both_silent_falls_to_base(artifact):
    artifact({"BTCUSD": {"direction_v4": None, "direction_backup": None}})
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)  # zemine düştü (dürüst)
    # İki motor da None → gözlem satırı YAZILMAZ (kıyaslanacak şey yok)
    assert not any(w.startswith("touche_observe") for w in res.warnings)


def test_no_artifact_is_byte_identical(monkeypatch, tmp_path):
    """Artifact yoksa (suite default): ne skor ne warning değişir — bayt-aynı."""
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))
    res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)
    assert not any(w.startswith("touche_observe") for w in res.warnings)
