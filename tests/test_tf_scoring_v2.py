"""touche_backup motoru (tf_scoring_v2) + canlı üretici testleri.

Owner kararı (2026-07-12): canlı teknik oy v4; v2 = touche_backup (yedek motor).
Kritik güvenceler: (1) collect_leans karnenin ölçtüğü sinyal kümesini reuse eder,
(2) signal_weights yalnız EDGE-kanıtlıya ağırlık verir (aday/INVERSE/yetersiz=0),
(3) direction_score katmanlı roller (yalnız 1d/4h yön üretir),
(4) regime_directed rejim-anahtarlı konuşmacı (UP→1d, DOWN→4h, vekâlet yok),
(5) üretici v4+backup yönlerini yan yana üretir; kanıtsız/az-bar → dürüst
    no_evidence, (6) flag OFF → no-op.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.learning import tf_scoring_shadow as producer
from packages.scoring import tf_scoring_v2 as v2


def _row(verdict, ratio, *, stable=True, beats=True):
    return {"verdict": verdict, "edge_ratio": ratio, "stable": stable,
            "beats_baseline": beats}


def _scorecard(per_tf_signals):
    return {"per_timeframe": {tf: {"signals": sig} for tf, sig in per_tf_signals.items()}}


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


def _down_bars(n=260):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i in range(n):
        px = 220 - i * 0.4 + 2.0 * math.sin(i / 4.0)
        out.append(OHLCVBar(symbol="X", timeframe="1d", ts=base + timedelta(days=i),
                            open=px, high=px * 1.01, low=px * 0.99, close=px, volume=1.0))
    return out


# ── collect_leans reuse (kopya yok) ──────────────────────────────────────────

def test_collect_leans_reuses_signal_modules():
    """collect_leans karnenin ölçtüğü sinyal kümesini üretir (isimler 1:1 eşleşir)."""
    leans = v2.collect_leans("1d", _bars(260))
    assert "trend" in leans and "structure" in leans
    assert all(-1.0 <= v <= 1.0 for v in leans.values())


def test_collect_leans_empty_bars():
    assert v2.collect_leans("1d", []) == {}


# ── touche_backup ağırlıkları: yalnız EDGE ───────────────────────────────────

def test_weights_edge_only():
    """EDGE → edge_ratio; INVERSE/FLAT/INSUFFICIENT → ağırlık YOK (aday-cap
    tasarımı söküldü — adaylar kenarı seyreltiyordu, walk-forward kanıtı)."""
    sc = _scorecard({"4h": {
        "structure": _row("EDGE", 0.25),
        "rsi_extreme": _row("INVERSE", -0.20),
        "rsi": _row("FLAT", 0.50),
        "macd": _row("INSUFFICIENT", 0.9),
    }})
    assert v2.signal_weights(sc, "4h") == {"structure": 0.25}


def test_weights_empty_scorecard_is_empty():
    assert v2.signal_weights({}, "1d") == {}
    assert v2.signal_weights(_scorecard({"1d": {}}), "1d") == {}


# ── direction_score: katmanlı roller ─────────────────────────────────────────

def test_direction_score_only_for_direction_tfs():
    """1h (MULTIPLIER) ve 15m (TRIGGER) yön skoru ÜRETMEZ (None)."""
    leans = {"structure": 1.0}
    weights = {"structure": 0.3}
    assert v2.direction_score("1h", leans, weights) is None
    assert v2.direction_score("15m", leans, weights) is None
    assert v2.direction_score("4h", leans, weights) == 1.0  # DIRECTION → üretir


def test_direction_score_none_without_evidence():
    """Kanıtlı ağırlık yoksa DIRECTION TF bile None (gürültü karara girmez)."""
    assert v2.direction_score("1d", {"trend": 0.9}, {}) is None


def test_direction_score_weighted_mean():
    """Skor = Σ(lean×w)/Σ(w), [−1,+1]'e kırpılı."""
    leans = {"trend": 1.0, "structure": -1.0}
    weights = {"trend": 0.3, "structure": 0.1}
    # (1.0*0.3 + -1.0*0.1) / 0.4 = 0.2/0.4 = 0.5
    assert v2.direction_score("1d", leans, weights) == pytest.approx(0.5)


# ── rejim-anahtarlı konuşmacı (v4.direction + backup reuse eder) ─────────────

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


# ── API endpoint (artifact-servis) ───────────────────────────────────────────

def test_endpoint_no_artifact_returns_no_data(tmp_path, monkeypatch):
    """GET /learning/tf-scoring-shadow: artifact yoksa NO_DATA (uydurma yok)."""
    from fastapi.testclient import TestClient

    from apps.api.main import app
    monkeypatch.delenv(producer.FLAG, raising=False)
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(tmp_path / "yok.json"))
    body = TestClient(app).get("/api/v1/learning/tf-scoring-shadow").json()
    assert body["status"] == "NO_DATA" and body["enabled"] is False


def test_endpoint_serves_artifact(tmp_path, monkeypatch):
    """Artifact varsa içerik aynen sunulur (v4+backup alanları dahil)."""
    import json

    from fastapi.testclient import TestClient

    from apps.api.main import app
    art = tmp_path / "sh.json"
    art.write_text(json.dumps({
        "generated_at": "2026-07-12T00:00:00+00:00",
        "engine": "tf_scoring_v4_live",
        "per_symbol": {"BTCUSD": {"status": "OK", "direction_v4": -0.7,
                                  "direction_backup": -0.4, "bias": "BEARISH",
                                  "regime": {"regime": "DOWN", "er": 0.23},
                                  "speaker_tf": "4h"}},
    }), encoding="utf-8")
    monkeypatch.setenv("TF_SCORING_V2_SHADOW_PATH", str(art))
    body = TestClient(app).get("/api/v1/learning/tf-scoring-shadow").json()
    assert body["status"] == "OK"
    assert body["per_symbol"]["BTCUSD"]["direction_v4"] == -0.7
    assert body["per_symbol"]["BTCUSD"]["direction_backup"] == -0.4


# ── Üretici (flag-gated, izole hesap) ────────────────────────────────────────

def test_producer_disabled_by_default(monkeypatch):
    """Flag yoksa run() no-op (learning koşusu bayt-eşdeğer)."""
    monkeypatch.delenv(producer.FLAG, raising=False)
    assert producer.run() == {"status": "DISABLED"}


def test_producer_up_regime_v4_and_backup(monkeypatch):
    """Yukarı seri + kanıtlı karne → hava UP → mikrofon 1d → v4 VE backup üretir."""
    monkeypatch.setenv(producer.FLAG, "1")
    monkeypatch.setattr(producer, "_load_scorecard", lambda: _scorecard({
        "1d": {"trend": _row("EDGE", 0.30)},
        "4h": {"structure": _row("EDGE", 0.25)},
    }))
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: _bars(260)
    )
    rep = producer.analyze(symbols=["BTCUSD"])
    assert rep["engine"] == "tf_scoring_v4_live"
    row = rep["per_symbol"]["BTCUSD"]
    assert row["status"] == "OK"
    assert row["regime"]["regime"] == "UP"       # yukarı seri → hava UP
    assert row["speaker_tf"] == "1d"             # UP → mikrofon 1d'de
    assert row["direction_backup"] is not None and row["direction_backup"] > 0
    if row["direction_v4"] is not None:          # v4 eşik-altıysa dürüst None
        assert -1.0 <= row["direction_v4"] <= 1.0


def test_producer_down_regime_speaker_is_4h(monkeypatch):
    """Düşen seri → hava DOWN → mikrofon 4h'de (konuşan TF damgası)."""
    monkeypatch.setenv(producer.FLAG, "1")
    monkeypatch.setattr(producer, "_load_scorecard", lambda: _scorecard({
        "4h": {"structure": _row("EDGE", 0.25)},
    }))
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: _down_bars(260)
    )
    rep = producer.analyze(symbols=["BTCUSD"])
    row = rep["per_symbol"]["BTCUSD"]
    assert row["regime"]["regime"] == "DOWN"
    assert row["speaker_tf"] == "4h"


def test_producer_insufficient_bars_no_evidence(monkeypatch):
    """Az bar → hiçbir motor yön üretemez → dürüst no_evidence (uydurma yok)."""
    monkeypatch.setenv(producer.FLAG, "1")
    monkeypatch.setattr(producer, "_load_scorecard", lambda: {})
    monkeypatch.setattr(
        "packages.data.providers.ohlcv.get_bars", lambda s, tf: _bars(50)
    )
    rep = producer.analyze(symbols=["BTCUSD"])
    row = rep["per_symbol"]["BTCUSD"]
    assert row["status"] == "no_evidence"
    assert row["direction_v4"] is None and row["direction_backup"] is None
