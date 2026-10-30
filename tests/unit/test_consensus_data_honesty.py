"""2026-07-13 dış denetim Basamak-2 — veri dürüstlüğü gölge dilimleri.

1. `min_module_coverage` (default 0.0 = KAPALI): modül düşünce _redistribute
   ağırlığı kalanlara şişiriyordu; kapsama = mevcut modüllerin TABAN ağırlık
   toplamı. Eşik altında yön NÖTRE zorlanır (işlem açılmaz); eksik-modüllü her
   hücrede `coverage_observe` kanıt satırı flag'siz.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.consensus import engine as ce
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import RegimeLayer, RegimeOutput


def _snap(direction_score: float = 60.0, rotation_status: str = "OK"):
    tech = SimpleNamespace(
        direction_score=direction_score, status="OK", timeframe="4h", score=direction_score
    )
    return SimpleNamespace(
        technicals_by_tf={"BTCUSD": {"4h": tech}},
        technicals={},
        # Haber kanıtsızken çekimser kalır; tam kapsama için sembole etkili tek başlık.
        headlines=[SimpleNamespace(verified=True, sentiment="neutral", asset_impact={"BTCUSD": 0.0})],
        rotation=SimpleNamespace(
            score=50.0, direction="neutral", evidence=[], status=rotation_status
        ),
        volatility={},
        derivatives={},
        options={},
    )


# OFFENSIVE default: quantum_regime_gate CANLI (2026-07-13) ve NEUTRAL'da
# quantum'u düşürür; bu testler quantum'u 5. modül olarak sayar → quantum'un
# konuştuğu (izinli) rejimde kurulur. Coverage/usage mantığı rejim-agnostik.
def _regime(label="OFFENSIVE"):
    return RegimeOutput(
        label=label,
        layers=[
            RegimeLayer(name="Likidite", score=55.0, direction="neutral", evidence=[]),
            RegimeLayer(name="Risk İştahı", score=60.0, direction="neutral", evidence=[]),
        ],
    )


@pytest.fixture(autouse=True)
def _no_artifact(tmp_path, monkeypatch):
    """touche kademesi artifact'ı bu testlere sızmasın (zemin motor)."""
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))


# Kapsama kapısı (min_module_coverage) bu dosyada İZOLE test edilir: eşik açıkça verilir.
_PIN = {"consensus": {"min_module_coverage": 0.0}}


# ── 1. min_module_coverage ───────────────────────────────────────────────────

def test_full_coverage_no_observe_line():
    with threshold_override(_PIN):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    assert len(res.modules) == 5
    assert not any(w.startswith("coverage_observe") for w in res.warnings)


def test_missing_module_writes_observe_flag_off():
    """Rotasyon UNAVAILABLE → quantum düşer → kapsama <1 gözlemi (applied=no);
    davranış değişmez (default 0.0 = bayt-aynı)."""
    with threshold_override(_PIN):
        res = ce.build("BTCUSD", _snap(80.0, rotation_status="UNAVAILABLE"), _regime(), "4h")
    assert not any(m.name == "quantum" for m in res.modules)
    line = next(w for w in res.warnings if w.startswith("coverage_observe"))
    assert ":applied=no" in line and ":min=0.00:" in line
    assert res.direction == "bullish"  # yön kısıtlanmadı


def test_coverage_gate_forces_neutral():
    """Eşik 0.95 + quantum eksik → kapsama eşiğin altında → yön nötre zorlanır;
    skor raporda aynen kalır (yalnız işlem-açıcı yön kısıtlanır)."""
    with threshold_override({"consensus": {"min_module_coverage": 0.95}}):
        gated = ce.build("BTCUSD", _snap(80.0, rotation_status="UNAVAILABLE"), _regime(), "4h")
    with threshold_override(_PIN):  # aynı koşullar, tek fark eşik
        free = ce.build("BTCUSD", _snap(80.0, rotation_status="UNAVAILABLE"), _regime(), "4h")
    assert free.direction == "bullish"
    assert gated.direction == "neutral"
    assert gated.confluence_aligned is False
    assert gated.score == free.score  # skor değişmez — yalnız yön kısıtı
    assert any(w == "coverage_gate:forced_neutral:was=bullish" for w in gated.warnings)
    assert any(":applied=yes" in w for w in gated.warnings if w.startswith("coverage_observe"))


def test_coverage_gate_inactive_when_full():
    """Eşik açık ama tüm modüller mevcut (kapsama 1.0) → kapı dokunmaz."""
    with threshold_override({"consensus": {"min_module_coverage": 0.95}}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    assert res.direction == "bullish"
    assert not any(w.startswith("coverage_gate") for w in res.warnings)
