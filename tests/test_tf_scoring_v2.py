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


# ── R4: API endpoint (artifact-servis, D5 deseni) ────────────────────────────

def test_endpoint_no_artifact_returns_no_data(tmp_path, monkeypatch):
    """GET /learning/tf-scoring-shadow: artifact yoksa NO_DATA (uydurma yok).
    apps.api.main import'u .env yükler → flag import SONRASI silinir."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    monkeypatch.delenv(shadow.FLAG, raising=False)
    monkeypatch.setattr(shadow, "_ART", str(tmp_path / "yok.json"))
    body = TestClient(app).get("/api/v1/learning/tf-scoring-shadow").json()
    assert body["status"] == "NO_DATA" and body["enabled"] is False


def test_endpoint_serves_artifact(tmp_path, monkeypatch):
    """Artifact varsa içerik aynen sunulur (çift-varyant alanlar dahil)."""
    import json

    from fastapi.testclient import TestClient

    from apps.api.main import app
    art = tmp_path / "sh.json"
    art.write_text(json.dumps({
        "generated_at": "2026-07-06T00:00:00+00:00",
        "engine": "tf_scoring_v2_shadow_r2",
        "per_symbol": {"BTCUSD": {"status": "OK", "direction": -0.7,
                                  "bias": "BEARISH",
                                  "regime": {"regime": "DOWN", "er": 0.23},
                                  "direction_blend_legacy": -0.65}},
    }), encoding="utf-8")
    monkeypatch.setattr(shadow, "_ART", str(art))
    body = TestClient(app).get("/api/v1/learning/tf-scoring-shadow").json()
    assert body["status"] == "OK"
    assert body["per_symbol"]["BTCUSD"]["regime"]["regime"] == "DOWN"
    assert body["per_symbol"]["BTCUSD"]["direction_blend_legacy"] == -0.65


# ── R2: rejim-anahtarlı birincil kural ───────────────────────────────────────

def test_regime_directed_up_only_1d_speaks():
    """UP havada mikrofon 1d'de — 4h skoru ne olursa olsun okunmaz."""
    assert v2.regime_directed({"1d": 0.8, "4h": -0.9}, "UP") == 0.8


def test_regime_directed_down_only_4h_speaks():
    """DOWN havada mikrofon 4h'de — 1d okunmaz."""
    assert v2.regime_directed({"1d": 0.8, "4h": -0.6}, "DOWN") == -0.6


def test_regime_directed_no_proxy_when_speaker_silent():
    """Konuşma hakkı olan TF kanıtsızsa diğeri VEKÂLET ALAMAZ (backtest böyle
    ölçüldü; kanıtsız vekâlet = ölçülmemiş tasarım)."""
    assert v2.regime_directed({"4h": 0.9}, "UP") is None      # 1d yok → None
    assert v2.regime_directed({"1d": 0.9}, "DOWN") is None    # 4h yok → None


def test_regime_directed_unknown_regime_is_none():
    assert v2.regime_directed({"1d": 0.8, "4h": 0.5}, None) is None
    assert v2.regime_directed({"1d": 0.8}, "SIDEWAYS") is None


def test_signal_weights_edge_only_mode_excludes_candidates():
    """R2: include_candidates=False → adaylar (FLAT+kararlı+taban) dışarıda,
    yalnız EDGE konuşur (adaylar kenarı seyreltiyordu — walk-forward kanıtı)."""
    sc = _scorecard({"1d": {
        "trend": _row("EDGE", 0.30),
        "rsi": _row("FLAT", 0.50),  # aday
    }})
    assert v2.signal_weights(sc, "1d", include_candidates=False) == {"trend": 0.30}
    assert "rsi" in v2.signal_weights(sc, "1d")  # default: aday hâlâ girer (legacy)


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
    assert rep["engine"].startswith("tf_scoring_v2_shadow")  # sürüm-dayanıklı
    assert rep["per_symbol"]["BTCUSD"]["status"] == "no_evidence"
    assert rep["per_symbol"]["BTCUSD"]["direction"] is None


def test_shadow_analyze_with_evidence_produces_direction(monkeypatch):
    """Kanıtlı karne (1d trend EDGE) + yukarı seri → hava UP → 1d konuşur →
    pozitif yön. Çift-varyant: kontrol (legacy harman) da kayıtta."""
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
    assert row["regime"]["regime"] == "UP"  # yukarı seri → hava UP
    assert row["direction"] is not None and row["bias"] == "BULLISH"
    # UP → mikrofon 1d'de: birincil yön 1d skoruna eşit (4h karışmaz)
    assert row["direction"] == row["tf_scores"]["1d"]
    assert row["direction_blend_legacy"] is not None  # kontrol grubu kayıtta
    assert "trend" in row["drivers"]["1d"]  # şeffaflık: hangi sinyal sürdü


def test_shadow_down_regime_speaker_is_4h(monkeypatch):
    """Düşen seri → hava DOWN → mikrofon 4h'de; 1d kanıtı olsa da okunmaz."""
    monkeypatch.setenv(shadow.FLAG, "1")
    monkeypatch.setattr(shadow, "_load_scorecard", lambda: _scorecard({
        "1d": {"trend": _row("EDGE", 0.30)},
        "4h": {"structure": _row("EDGE", 0.25)},
    }))
    # Düşen dalgalı seri (zaman ileri, fiyat aşağı) → hava DOWN + yapı pivotları
    base = datetime(2026, 1, 1, tzinfo=UTC)
    down_bars = []
    for i in range(260):
        px = 220 - i * 0.4 + 2.0 * math.sin(i / 4.0)
        down_bars.append(OHLCVBar(symbol="X", timeframe="1d", ts=base + timedelta(days=i),
                                  open=px, high=px * 1.01, low=px * 0.99, close=px,
                                  volume=1.0))
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: down_bars
    )
    rep = shadow.analyze(symbols=["BTCUSD"])
    row = rep["per_symbol"]["BTCUSD"]
    assert row["regime"]["regime"] == "DOWN"
    if row["status"] == "OK":  # 4h yapı okuma üretebildiyse
        assert row["direction"] == row["tf_scores"]["4h"]
