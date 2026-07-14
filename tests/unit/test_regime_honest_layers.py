"""F2-3 + M2 — rejim katmanı veri dürüstlüğü testleri.

- Flag KAPALI (default): eksik makro veri eski default'larla doldurulur —
  davranış bayt-aynı (regresyon), dropped hep boş.
- Flag AÇIK: veri olmayan katman DÜŞER (sahte skor yok); ortalama kalanlardan.
- Consensus: katmansız kalan fundamental/sentinel modülü düşer, ağırlık
  redistribute edilir (quantum deseni), warning yazılır.
- M2: rejim-makro fiyatı eksikse snapshot warning listesine girer (flag'siz).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.data.ingestion.pipeline import _regime_macro_missing
from packages.data.registry.loader import threshold_override
from packages.regime.classifier import classify

_FLAG_ON = {"regime": {"drop_unavailable_layers": True}}


def _q(symbol: str, price: float | None):
    return SimpleNamespace(symbol=symbol, price=price)


def _snap(prices=(), technicals=None, rotation_status="OK", rotation_score=42.0):
    return SimpleNamespace(
        prices=list(prices),
        technicals=technicals or {},
        rotation=SimpleNamespace(
            score=rotation_score, direction="neutral", evidence=["ev"], status=rotation_status
        ),
    )


_FULL_MACRO = (
    _q("DXY", 101.0), _q("US10Y", 4.4), _q("US02Y", 4.1), _q("VIX", 17.0), _q("CPI", 334.0),
)


# ------------------------- flag KAPALI (regresyon) ---------------------------

def test_flag_off_uses_legacy_defaults() -> None:
    """Makro veri tamamen yokken eski default'lar birebir: Likidite 90.5
    (DXY 104 / US10Y 4.3), Risk İştahı 92.0 (VIX 14). Hiçbir katman düşmez."""
    out = classify(_snap())
    assert out.dropped == []
    by = {ly.name: ly.score for ly in out.layers}
    assert by["Likidite"] == 90.5
    assert by["Risk İştahı"] == 92.0
    assert by["Kripto Momentum"] == 50.0
    assert by["Sermaye Rotasyonu"] == 42.0


def test_flag_off_real_data_same_as_flag_on() -> None:
    """Tüm veriler mevcutken flag'in hiçbir etkisi yok (skorlar aynı)."""
    btc_tech = SimpleNamespace(score=53.6, rsi=53.2, ema_stack="bearish")
    snap = _snap(prices=_FULL_MACRO, technicals={"BTCUSD": btc_tech})
    off = classify(snap)
    with threshold_override(_FLAG_ON):
        on = classify(snap)
    assert [(ly.name, ly.score) for ly in off.layers] == [
        (ly.name, ly.score) for ly in on.layers
    ]
    assert on.dropped == []


# --------------------------- flag AÇIK (dürüst mod) --------------------------

def test_flag_on_drops_layers_without_data() -> None:
    with threshold_override(_FLAG_ON):
        out = classify(_snap(rotation_status="UNAVAILABLE"))
    assert set(out.dropped) == {
        "Likidite", "Risk İştahı", "Kripto Momentum", "Sermaye Rotasyonu"
    }
    assert out.layers == []
    assert out.label == "NEUTRAL"  # skor uydurulmaz; etiket tarafsız fallback


def test_flag_on_average_over_remaining_layers() -> None:
    """Yalnız VIX var → tek katman (Risk İştahı 80) → ortalama 80 → OFFENSIVE."""
    with threshold_override(_FLAG_ON):
        out = classify(_snap(prices=[_q("VIX", 17.0)], rotation_status="UNAVAILABLE"))
    assert [ly.name for ly in out.layers] == ["Risk İştahı"]
    assert out.layers[0].score == 80.0
    assert out.label == "OFFENSIVE"
    assert "Likidite" in out.dropped


def test_flag_on_partial_curve_skipped_not_faked() -> None:
    """DXY+US10Y gerçek ama US02Y yok → katman kalır, eğri sinyali atlanır
    (yarısı uydurma 2s10s hesaplanmaz)."""
    with threshold_override(_FLAG_ON):
        out = classify(_snap(prices=[_q("DXY", 101.0), _q("US10Y", 4.4)]))
    liq = next(ly for ly in out.layers if ly.name == "Likidite")
    assert any("2s10s veri yok" in e for e in liq.evidence)
    # score = 100 − 1×2 − 0.4×5 = 96.0 (eğri cezası yok)
    assert liq.score == pytest.approx(96.0)


# ------------------------ consensus modül düşürme ----------------------------

def test_consensus_drops_fundamental_and_sentinel_when_layerless(monkeypatch) -> None:
    from packages.consensus import engine as ce
    from packages.regime.classifier import RegimeOutput

    # OFFENSIVE: quantum_regime_gate CANLI NEUTRAL'da quantum'u düşürür; bu test
    # quantum'un KALDIĞINI bekler → quantum'un konuştuğu izinli rejimde kur.
    regime = RegimeOutput(label="OFFENSIVE", layers=[], dropped=["Likidite", "Risk İştahı"])
    snap = _snap(rotation_status="OK", rotation_score=42.0)
    snap.technicals_by_tf = None
    snap.headlines = []
    res = ce.build("BTCUSD", snap, regime, "1d")
    names = {m.name for m in res.modules}
    assert "fundamental" not in names
    assert "sentinel" not in names
    assert {"touche", "news", "quantum"} <= names
    # redistribute: kalan ağırlıklar 1'e normalize
    assert sum(m.weight for m in res.modules) == pytest.approx(1.0, abs=1e-3)
    assert any(w.startswith("fundamental_dropped:") for w in res.warnings)
    assert any(w.startswith("sentinel_dropped:") for w in res.warnings)


def test_consensus_unchanged_when_layers_present() -> None:
    """Katmanlar doluyken (flag kapalı normal akış) 5 modül de girer — regresyon."""
    from packages.consensus import engine as ce

    regime = classify(_snap(prices=_FULL_MACRO))
    snap = _snap(rotation_status="OK", rotation_score=42.0)
    snap.technicals_by_tf = None
    snap.headlines = []
    res = ce.build("BTCUSD", snap, regime, "1d")
    assert {m.name for m in res.modules} == {
        "touche", "fundamental", "news", "sentinel", "quantum"
    }
    assert not any("dropped" in w for w in res.warnings)


# ----------------------------------- M2 --------------------------------------

def test_macro_missing_helper_lists_only_missing() -> None:
    prices = [_q("DXY", 101.0), _q("US10Y", None), _q("VIX", None), _q("BTCUSD", None)]
    assert _regime_macro_missing(prices) == ["US10Y", "VIX"]
    assert _regime_macro_missing([_q("US10Y", 4.4)]) == []
