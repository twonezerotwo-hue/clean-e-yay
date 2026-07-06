"""R-serisi terfi — touche v2 (tf_scoring_v2 rejim-anahtarlı teknik yön) testleri.

- `_touche_v2`: gölge artifact'tan yön → 0-100 mapping; eksik/bayat/yönsüz → None.
- Flag KAPALI (default): canlı teknik oy v1 (bayt-aynı); v2 yalnız gözlem satırında.
- Flag AÇIK: canlı teknik oy v2; v2 kanıtsız/bayatsa v1'e düşer (dürüst).
- RiskGate/boyut/manuel kuyruk bu terfiden ETKİLENMEZ (yalnız yön oyu değişir).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override

_FLAG_ON = {"consensus": {"touche_v2": True}}


def _write_artifact(path, per_symbol: dict, *, age_sec: float = 0.0) -> None:
    gen = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
    path.write_text(
        json.dumps({"generated_at": gen, "per_symbol": per_symbol}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """Gölge artifact'ı tmp yola yönlendir; yazıcı fonksiyonu döndür."""
    p = tmp_path / "tf_scoring_v2_shadow.json"
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(p))
    return lambda per_symbol, **kw: _write_artifact(p, per_symbol, **kw)


# ── _touche_v2 birim (okuma + mapping) ───────────────────────────────────────

def test_touche_v2_maps_direction_to_0_100(artifact):
    artifact({"BTCUSD": {"direction": 0.4}})       # 50 + 0.4*50 = 70
    assert ce._touche_v2("BTCUSD") == pytest.approx(70.0)
    artifact({"BTCUSD": {"direction": -0.6}})      # 50 - 30 = 20
    assert ce._touche_v2("BTCUSD") == pytest.approx(20.0)


def test_touche_v2_missing_artifact_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))
    assert ce._touche_v2("BTCUSD") is None


def test_touche_v2_stale_artifact_falls_back(artifact):
    # Öğrenme worker'ı durmuş → 3h+ bayat artifact → None (v1'e düş).
    artifact({"BTCUSD": {"direction": 0.4}}, age_sec=4 * 3600)
    assert ce._touche_v2("BTCUSD") is None


def test_touche_v2_no_direction_is_none(artifact):
    artifact({"BTCUSD": {"direction": None}})      # rejim/kanıt yok
    assert ce._touche_v2("BTCUSD") is None
    artifact({"ETHUSD": {"direction": 0.5}})       # başka sembol
    assert ce._touche_v2("BTCUSD") is None


def test_touche_v2_clamps(artifact):
    artifact({"BTCUSD": {"direction": 5.0}})       # taşma → 100'e kıstırılır
    assert ce._touche_v2("BTCUSD") == pytest.approx(100.0)


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


def test_flag_off_live_touche_is_v1_with_observe_line(artifact):
    artifact({"BTCUSD": {"direction": 0.4}})       # v2 = 70
    res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)     # v1 CANLI (bayt-aynı)
    assert any(w == "touche_v2_observe:v1=60.0:v2=70.0:used=v1" for w in res.warnings)


def test_flag_on_live_touche_is_v2(artifact):
    artifact({"BTCUSD": {"direction": 0.4}})       # v2 = 70
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(70.0)     # v2 CANLI
    assert any(w == "touche_v2_observe:v1=60.0:v2=70.0:used=v2" for w in res.warnings)


def test_flag_on_no_evidence_falls_back_to_v1(artifact):
    artifact({"BTCUSD": {"direction": None}})      # v2 yok
    with threshold_override(_FLAG_ON):
        res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)     # v1'e düştü (dürüst)
    # v2 None → gözlem satırı YAZILMAZ (kıyaslanacak şey yok)
    assert not any(w.startswith("touche_v2_observe") for w in res.warnings)


def test_flag_off_no_artifact_is_byte_identical(monkeypatch, tmp_path):
    """Artifact yoksa (suite default): ne skor ne warning değişir — bayt-aynı."""
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))
    res = ce.build("BTCUSD", _snap(60.0), _regime(), "4h")
    touche = next(m for m in res.modules if m.name == "touche")
    assert touche.score == pytest.approx(60.0)
    assert not any(w.startswith("touche_v2_observe") for w in res.warnings)
