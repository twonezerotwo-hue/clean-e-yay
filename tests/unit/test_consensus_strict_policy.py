"""Canlı karar yolu: eksik modülde sabit ağırlık (missing_module_policy: fixed).

Bu yol pytest altında kendini kapatıyordu, canlıda koşan dal hiç sınanmıyordu.
Burada yalnız süreç bayrağı (`_canonical_runtime_enabled`) açılır; filigran,
config modu ve konsensüs hesabı gerçek koduyla koşar. Hepsi offline.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput

AFTER = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
BEFORE = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
# İlgisiz canlı bayraklar pinlenir; yalnız eksik modül politikası değişken.
_BASE = {
    "news_abstain": False,
    "min_module_coverage": 0.0,
    "timeframe_module_drop": {"4h": []},
}


def _cfg(mode: str = "fixed", active_after: str = "2026-10-30T00:00:00+00:00") -> dict:
    return {"consensus": {**_BASE, "missing_module_policy": {"mode": mode, "active_after": active_after}}}


def _snap(generated_at, rotation_status: str = "OK", direction_score: float = 80.0):
    tech = SimpleNamespace(direction_score=direction_score, status="OK", timeframe="4h", score=direction_score)
    return SimpleNamespace(
        generated_at=generated_at,
        technicals_by_tf={"BTCUSD": {"4h": tech}},
        technicals={},
        headlines=[],
        rotation=SimpleNamespace(score=50.0, direction="neutral", evidence=[], status=rotation_status),
        volatility={},
        derivatives={},
        options={},
    )


def _regime(label: str = "OFFENSIVE"):
    return RegimeOutput(
        label=label,
        layers=[
            RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ],
    )


@pytest.fixture(autouse=True)
def _no_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(ce, "_canonical_runtime_enabled", lambda: True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), (" ON ", True), ("yes", True), ("0", False), ("", False), ("off", False)],
)
def test_runtime_flag_parses_env(monkeypatch, value, expected):
    # AWS ile yerel aynı değeri farklı yazsa bile (1/true/on) aynı yol seçilir.
    monkeypatch.setattr(ce, "sys", SimpleNamespace(modules={}))
    monkeypatch.setenv("E_YAY_CANONICAL_RUNTIME", value)
    assert ce._canonical_runtime_enabled() is expected


def test_runtime_flag_is_off_under_pytest(monkeypatch):
    monkeypatch.setenv("E_YAY_CANONICAL_RUNTIME", "1")
    assert ce._canonical_runtime_enabled() is False


def test_policy_respects_watermark_and_mode(live):
    with threshold_override(_cfg()):
        assert ce._strict_missing_modules_active(AFTER) is True
        assert ce._strict_missing_modules_active(BEFORE) is False
        assert ce._strict_missing_modules_active(None) is False
        assert ce._strict_missing_modules_active(AFTER.replace(tzinfo=None)) is True
    with threshold_override(_cfg(mode="redistribute")):
        assert ce._strict_missing_modules_active(AFTER) is False


def test_missing_data_module_counts_as_neutral(live):
    # Rotasyon verisi yok → quantum VERİ eksiği: kendi ağırlığıyla nötr 50 sayılır,
    # kalanlara ağırlık şişirilmez ve hücre nötre zorlanır.
    with threshold_override(_cfg()):
        strict = ce.build("BTCUSD", _snap(AFTER, rotation_status="UNAVAILABLE"), _regime(), "4h")
        legacy = ce.build("BTCUSD", _snap(BEFORE, rotation_status="UNAVAILABLE"), _regime(), "4h")
    assert not any(m.name == "quantum" for m in strict.modules)
    assert "missing_module_policy:fixed:neutral_fill=quantum" in strict.warnings
    assert "coverage_gate:forced_neutral:reason=missing_module" in strict.warnings
    assert strict.direction == "neutral"
    filled = 1.0 - sum(m.weight for m in strict.modules)
    assert 0.0 < filled < 1.0
    expected = sum(m.score * m.weight for m in strict.modules) + 50.0 * filled
    assert strict.score == pytest.approx(expected, abs=0.2)
    # Ölçek korunur: skor eski (yeniden dağıtan) skordan 50'ye doğru çekilir, aşağı kaymaz.
    assert 50.0 < strict.score < legacy.score
    # Filigrandan önceki anlık görüntü eski yolu korur.
    assert legacy.direction == "bullish"
    assert sum(m.weight for m in legacy.modules) == pytest.approx(1.0, abs=1e-3)
    assert not any(w.startswith("missing_module_policy") for w in legacy.warnings)


def test_policy_drop_is_not_missing_data(live):
    # Rejim kapısı quantum'u bilinçli düşürür: eksik veri sayılmaz, yön nötre zorlanmaz,
    # ağırlıklar eskisi gibi kalanlara dağılır (canlıda bugün 80 hücreyi nötre çeken hata).
    with threshold_override(_cfg()):
        res = ce.build("BTCUSD", _snap(AFTER), _regime("DEFENSIVE"), "4h")
    assert any(w.startswith("quantum_dropped:regime_gate") for w in res.warnings)
    assert not any(w.startswith("missing_module_policy") for w in res.warnings)
    assert not any(w.startswith("coverage_gate:forced_neutral") for w in res.warnings)
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)


def test_timeframe_drop_is_not_missing_data(live):
    cfg = _cfg()
    cfg["consensus"]["timeframe_module_drop"] = {"active_after": "2026-10-29T00:00:00+00:00", "4h": ["fundamental"]}
    with threshold_override(cfg):
        res = ce.build("BTCUSD", _snap(AFTER), _regime(), "4h")
    assert any(w.startswith("timeframe_module_drop:4h:fundamental") for w in res.warnings)
    assert not any(w.startswith("missing_module_policy") for w in res.warnings)
    assert res.direction == "bullish"


def test_full_coverage_is_unchanged_by_policy(live, monkeypatch):
    with threshold_override(_cfg()):
        strict = ce.build("BTCUSD", _snap(AFTER), _regime(), "4h")
    monkeypatch.setattr(ce, "_canonical_runtime_enabled", lambda: False)
    with threshold_override(_cfg()):
        off = ce.build("BTCUSD", _snap(AFTER), _regime(), "4h")
    assert strict.direction == off.direction == "bullish"
    assert strict.score == off.score
    assert not any(w.startswith("missing_module_policy") for w in strict.warnings)


def test_forced_neutral_consensus_never_opens(monkeypatch):
    # Nötre zorlanan hücrede skor tek başına pozisyon açmaz (owner kararı 2026-10-30);
    # eskiden "neutral signal" gerekçesiyle short açılıyordu.
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    fake = ConsensusResult(
        symbol="BTCUSD", score=20.0, direction="neutral", confluence_aligned=False,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=20.0, weight=1.0, contribution=20.0)],
        warnings=["coverage_gate:forced_neutral:reason=missing_module"],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, classify(snap), hold_risk, equity_usd=100_000)
    assert d.candidate_action == "open_short"
    assert d.action == "hold"
    assert "coverage_gate:forced_neutral" in d.blocked_by
