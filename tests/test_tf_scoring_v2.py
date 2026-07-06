"""tf_scoring_v2 + gölge üretici testleri (D6, İZOLE salt-gözlem).

Kritik güvenceler: (1) kanıt-cap kuralı (EDGE→tam, aday→cap, INVERSE/yetersiz→0),
(2) katmanlı roller (yalnız 1d/4h yön üretir), (3) sabit-olmayan kanıt-güdümlü
harman (kanıtı güçlü TF baskın), (4) ters ölçülen sinyal yöne ASLA sızmaz,
(5) gölge üretici flag OFF → no-op (bayt-eşdeğer).
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import tf_scoring_shadow as shadow
from packages.scoring import tf_scoring_v2 as v2


def _row(verdict, ratio, *, stable=True, beats=True):
    return {"verdict": verdict, "edge_ratio": ratio, "stable": stable,
            "beats_baseline": beats}


def _scorecard(per_tf_signals):
    return {"per_timeframe": {tf: {"signals": sig} for tf, sig in per_tf_signals.items()}}


# ── Kanıt-cap kuralı ─────────────────────────────────────────────────────────

def test_weights_edge_full_inverse_zero():
    """EDGE → tam (edge_ratio); INVERSE → 0 (ters sinyal yöne asla)."""
    sc = _scorecard({"4h": {
        "structure": _row("EDGE", 0.25),
        "rsi_extreme": _row("INVERSE", -0.20),
    }})
    w = v2.signal_weights(sc, "4h")
    assert w == {"structure": 0.25}  # INVERSE düştü


def test_weights_candidate_capped():
    """Aday (FLAT + kararlı + tabanı geçen + pozitif) → CANDIDATE_CAP ile sınırlı."""
    sc = _scorecard({"1d": {
        "trend": _row("EDGE", 0.30),
        "rsi": _row("FLAT", 0.50),  # umutlu ama kanıtsız → cap
    }})
    w = v2.signal_weights(sc, "1d")
    assert w["trend"] == 0.30
    assert w["rsi"] == v2.CANDIDATE_CAP  # 0.50 değil, cap'lendi


def test_weights_unstable_flat_excluded():
    """FLAT ama kararsız / tabanı geçmeyen → ağırlık yok (aday sayılmaz)."""
    sc = _scorecard({"1d": {
        "a": _row("FLAT", 0.5, stable=False),
        "b": _row("FLAT", 0.5, beats=False),
        "c": _row("INSUFFICIENT", 0.9),
    }})
    assert v2.signal_weights(sc, "1d") == {}


# ── Katmanlı roller ──────────────────────────────────────────────────────────

def test_direction_score_only_for_direction_tfs():
    """1h (MULTIPLIER) ve 15m (TRIGGER) yön skoru ÜRETMEZ (None)."""
    leans = {"structure": 1.0}
    weights = {"structure": 0.3}
    assert v2.direction_score("1h", leans, weights) is None
    assert v2.direction_score("15m", leans, weights) is None
    assert v2.direction_score("4h", leans, weights) == 1.0  # DIRECTION → üretir


def test_direction_score_none_without_evidence():
    """Kanıtlı/aday ağırlık yoksa DIRECTION TF bile None (gürültü karara girmez)."""
    assert v2.direction_score("1d", {"trend": 0.9}, {}) is None


def test_direction_score_weighted_mean():
    """Skor = Σ(lean×w)/Σ(w), [−1,+1]'e kırpılı."""
    leans = {"trend": 1.0, "structure": -1.0}
    weights = {"trend": 0.3, "structure": 0.1}
    # (1.0*0.3 + -1.0*0.1) / 0.4 = 0.2/0.4 = 0.5
    assert v2.direction_score("1d", leans, weights) == pytest.approx(0.5)


# ── Kanıt-güdümlü harman (sabit oran YOK) ────────────────────────────────────

def test_blend_evidence_weighted_not_fixed():
    """1d kanıtı 4h'den güçlüyse harman 1d'ye kayar (sabit 0.55/0.45 değil)."""
    scores = {"1d": 1.0, "4h": -1.0}
    convictions = {"1d": 0.30, "4h": 0.10}  # 1d üç kat kanıtlı
    # (1.0*0.30 + -1.0*0.10) / 0.40 = 0.20/0.40 = 0.5 (1d baskın → pozitif)
    assert v2.blended_direction(scores, convictions) == pytest.approx(0.5)


def test_blend_none_when_no_direction_evidence():
    """Hiçbir DIRECTION TF kanıt üretmediyse harman None (dürüst: yön yok)."""
    assert v2.blended_direction({}, {}) is None
    assert v2.blended_direction({"1d": 0.8}, {"1d": 0.0}) is None  # conviction 0


# ── collect_leans reuse (kopya yok) ──────────────────────────────────────────

def _bars(n, start=100.0, step=0.4):
    """Salınımlı YUKARI seri: net uptrend (EMA'lar yukarı dizili → trend=+1) +
    hafif sinüs dalgası (fraktal pivotlar oluşsun → market_structure HH/HL okur)."""
    out = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        px = start + i * step + 2.0 * math.sin(i / 4.0)  # trend + dalga
        out.append(OHLCVBar(symbol="X", timeframe="1d", ts=base + timedelta(days=i),
                            open=px, high=px * 1.01, low=px * 0.99, close=px, volume=1.0))
    return out


def test_collect_leans_reuses_signal_modules():
    """collect_leans karnenin ölçtüğü sinyal kümesini üretir (isimler 1:1 eşleşir)."""
    leans = v2.collect_leans("1d", _bars(260))
    assert "trend" in leans and "structure" in leans
    assert all(-1.0 <= v <= 1.0 for v in leans.values())


def test_collect_leans_empty_bars():
    assert v2.collect_leans("1d", []) == {}


# ── Gölge üretici (flag-gated, izole) ────────────────────────────────────────

def test_shadow_disabled_by_default(monkeypatch):
    """Flag yoksa run() no-op (learning koşusu bayt-eşdeğer)."""
    monkeypatch.delenv(shadow.FLAG, raising=False)
    assert shadow.run() == {"status": "DISABLED"}


def test_shadow_analyze_no_evidence_is_honest(monkeypatch, tmp_path):
    """Karne kanıtı yokken semboller 'no_evidence' (v2 sahte yön uydurmaz)."""
    monkeypatch.setenv(shadow.FLAG, "1")
    # Boş karne → _load_scorecard boş dict döndürür (artifact yok)
    monkeypatch.setattr(shadow, "_load_scorecard", lambda: {})
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: _bars(260)
    )
    rep = shadow.analyze(symbols=["BTCUSD"])
    assert rep["engine"] == "tf_scoring_v2_shadow"
    assert rep["per_symbol"]["BTCUSD"]["status"] == "no_evidence"
    assert rep["per_symbol"]["BTCUSD"]["direction"] is None


def test_shadow_analyze_with_evidence_produces_direction(monkeypatch):
    """Kanıtlı karne (1d trend EDGE) + yukarı seri → v2 pozitif yön üretir."""
    monkeypatch.setenv(shadow.FLAG, "1")
    monkeypatch.setattr(shadow, "_load_scorecard", lambda: _scorecard({
        "1d": {"trend": _row("EDGE", 0.30)},
        "4h": {"structure": _row("EDGE", 0.25)},
    }))
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: _bars(260)
    )
    rep = shadow.analyze(symbols=["BTCUSD"])
    row = rep["per_symbol"]["BTCUSD"]
    assert row["status"] == "OK"
    assert row["direction"] is not None and row["bias"] == "BULLISH"
    assert "1d" in row["tf_scores"]  # DIRECTION TF skoru var
    assert "trend" in row["drivers"]["1d"]  # şeffaflık: hangi sinyal sürdü
