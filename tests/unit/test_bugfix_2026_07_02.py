"""Bugfix paketi (2026-07-02, owner onayı) regresyon testleri.

1. Confluence yön-farkındalığı: 3 modül sinyalin TERSİNE hizalıyken
   confluence_aligned=False (eski kod True diyordu → boyut yarılaması atlanıyordu).
2. Kapı çarpanı tabanı: penalty_gain>1 config'lense bile yön flip edemez.
3. reliability_bins son kova: tüm veri setini çifte saymaz.
4. missed-opp mfe_r 20R'de kırpılır.
"""
from __future__ import annotations

from packages.data.providers.technical import timeframe as tf
from packages.learning.calibration import reliability_bins


def test_confluence_requires_agreement_with_signal_side(monkeypatch):
    from packages.consensus import engine as ce

    # touche çok bearish + fundamental bearish → final bearish; news/sentinel/
    # quantum bullish (3 modül TERS tarafta). Eski kod: confluence=True (bug).
    def fake_scores():
        return {"touche": 15.0, "fundamental": 40.0, "news": 60.0,
                "sentinel": 70.0, "quantum": 60.0}

    monkeypatch.setattr(ce, "_touche", lambda *a, **k: (15.0, []))
    monkeypatch.setattr(ce, "_fundamental", lambda r: 40.0)
    monkeypatch.setattr(ce, "_fundamental_v2", lambda r: 40.0)
    monkeypatch.setattr(ce, "_news", lambda s, sym=None: 60.0)
    monkeypatch.setattr(ce, "_sentinel", lambda r: 70.0)
    monkeypatch.setattr(ce, "_sentinel_v2", lambda *a: 70.0)
    monkeypatch.setattr(ce, "_quantum", lambda s: 60.0)

    from types import SimpleNamespace
    snap = SimpleNamespace(rotation=SimpleNamespace(status="OK", score=60.0),
                           technicals_by_tf={}, technicals={}, headlines=[])
    regime = SimpleNamespace(label="NEUTRAL", layers=[], dropped=[])
    res = ce.build("BTCUSD", snap, regime)
    assert res.direction == "bearish"
    assert res.confluence_aligned is False  # 3 bullish modül SHORT'u desteklemiyor


def test_confluence_true_when_modules_agree_with_side(monkeypatch):
    from types import SimpleNamespace

    from packages.consensus import engine as ce

    monkeypatch.setattr(ce, "_touche", lambda *a, **k: (25.0, []))
    monkeypatch.setattr(ce, "_fundamental", lambda r: 30.0)
    monkeypatch.setattr(ce, "_fundamental_v2", lambda r: 30.0)
    monkeypatch.setattr(ce, "_news", lambda s, sym=None: 40.0)
    monkeypatch.setattr(ce, "_sentinel", lambda r: 60.0)
    monkeypatch.setattr(ce, "_sentinel_v2", lambda *a: 60.0)
    monkeypatch.setattr(ce, "_quantum", lambda s: 55.0)

    snap = SimpleNamespace(rotation=SimpleNamespace(status="OK", score=55.0),
                           technicals_by_tf={}, technicals={}, headlines=[])
    regime = SimpleNamespace(label="NEUTRAL", layers=[], dropped=[])
    res = ce.build("BTCUSD", snap, regime)
    assert res.direction == "bearish"
    assert res.confluence_aligned is True  # touche+fundamental+news ≤45


def test_gate_mult_floor_prevents_direction_flip():
    # penalty_gain=2.0 (config kazası) + tam çelişki → çarpan 0'da tabanlanır,
    # skor en fazla 50'ye çöker, yön ASLA ters çevrilmez.
    from packages.data.types import FibonacciAnalysis, TechnicalReversalSignals
    cfg = tf.TechnicalConfig(tilt_penalty_gain=2.0)
    s, diag = tf._direction_score(
        70.0, 0.0, "bullish",
        fib=FibonacciAnalysis(timeframe="1D", zone="breakdown", validity="sane"),
        reversal=TechnicalReversalSignals(bias="BEARISH"),
        cfg=cfg,
    )
    assert s is not None and s >= 50.0
    assert diag["gate_mult"] >= 0.0


def test_reliability_bins_no_double_count():
    samples = [(0.1, True)] * 3 + [(0.3, False)] * 4 + [(1.0, True)] * 2
    bins = reliability_bins(samples, n_bins=5)
    assert sum(b.count for b in bins) == len(samples)  # eski kodda 9+9=18 çıkardı
    assert bins[-1].count == 2  # yalnız p∈[0.8,1.0]


def test_mfe_r_clamped():
    from datetime import UTC, datetime

    from packages.learning.missed_opportunity import _resolve_event
    ev = _resolve_event({}, "missed_win", datetime.now(UTC), 250.176, 1)
    assert ev["mfe_r"] == 20.0
    ev2 = _resolve_event({}, "avoided_loss", datetime.now(UTC), 0.47, 1)
    assert ev2["mfe_r"] == 0.47
