"""2026-07-13 dış denetim Basamak-2 — veri dürüstlüğü gölge dilimleri.

1. `min_module_coverage` (default 0.0 = KAPALI): modül düşünce _redistribute
   ağırlığı kalanlara şişiriyordu; kapsama = mevcut modüllerin TABAN ağırlık
   toplamı. Eşik altında yön NÖTRE zorlanır (işlem açılmaz); eksik-modüllü her
   hücrede `coverage_observe` kanıt satırı flag'siz.
2. `enforce_decision_usage` (default false): source_registry'nin
   analytics_only (news) / simulation_only (rotation→quantum) etiketleri
   uygulanır — kısıtlı modül yön kararına girmez; kapalıyken
   `decision_usage_observe` kanıt satırı flag'siz.
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
        headlines=[],
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


# 2026-07-13 aktivasyonları: news_abstain + min_module_coverage artık CANLI.
# Bu dosya M10/M11 semantiğini İZOLE test eder → ilgisiz canlı flag'ler pinlenir
# (testler config-default'a bağımlı kalmasın).
_PIN = {"consensus": {"news_abstain": False, "min_module_coverage": 0.0}}


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
    with threshold_override({"consensus": {"min_module_coverage": 0.95, "news_abstain": False}}):
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
    with threshold_override({"consensus": {"min_module_coverage": 0.95, "news_abstain": False}}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    assert res.direction == "bullish"
    assert not any(w.startswith("coverage_gate") for w in res.warnings)


# ── 2. enforce_decision_usage ────────────────────────────────────────────────

def test_restricted_modules_from_registry():
    """Gerçek registry: news=analytics_only, quantum(rotation)=simulation_only."""
    restricted = ce._restricted_modules()
    assert restricted.get("news") == "analytics_only"
    assert restricted.get("quantum") == "simulation_only"
    assert "touche" not in restricted and "fundamental" not in restricted


def test_usage_flag_off_observe_only():
    with threshold_override({"consensus": {"news_abstain": False, "min_module_coverage": 0.0,
                                           "enforce_decision_usage": False}}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    line = next(w for w in res.warnings if w.startswith("decision_usage_observe"))
    assert "news=analytics_only" in line and "quantum=simulation_only" in line
    assert line.endswith(":applied=no")
    names = {m.name for m in res.modules}
    assert {"news", "quantum"} <= names  # modüller hâlâ oyda (bayt-aynı)


def test_usage_flag_on_drops_restricted_modules():
    with threshold_override({"consensus": {"enforce_decision_usage": True, "news_abstain": False}}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    names = {m.name for m in res.modules}
    assert names == {"touche", "fundamental", "sentinel"}
    assert "decision_usage_dropped:news:analytics_only" in res.warnings
    assert "decision_usage_dropped:quantum:simulation_only" in res.warnings
    # Kalan ağırlıklar 1'e normalize (redistribute korunur)
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)


def test_usage_drop_lowers_coverage():
    """Düşürülen modüller kapsamayı da düşürür — iki dürüstlük katmanı bileşik:
    enforcement + sıkı eşik → yön nötre zorlanır."""
    with threshold_override({"consensus": {
        "enforce_decision_usage": True, "min_module_coverage": 0.95,
    }}):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    assert res.direction == "neutral"
    assert any(w.startswith("coverage_gate:forced_neutral") for w in res.warnings)


def test_registry_unreadable_is_safe(monkeypatch):
    """Registry okunamazsa kısıt uygulanmaz (boş dict) — motor çalışmaya devam."""
    monkeypatch.setattr(ce, "load_source_registry", lambda: (_ for _ in ()).throw(OSError()))
    assert ce._restricted_modules() == {}
    with threshold_override(_PIN):
        res = ce.build("BTCUSD", _snap(80.0), _regime(), "4h")
    assert len(res.modules) == 5
    assert not any(w.startswith("decision_usage_observe") for w in res.warnings)
