"""Rotasyon motoru + sağlayıcı testleri (P0 legacy parity).

- engine.compute deterministik skor üretir.
- Veri yetersizse UNAVAILABLE (mock üretmez, crash yok).
- "Identical returns" sanity guard tetiklenir.
- Provider fixture (TEST_USE_MOCK) modunda OK döner.
- Rotasyon UNAVAILABLE → consensus quantum modülü düşer (redistribute).
"""
from __future__ import annotations

import math


def _series(base: float, drift: float, n: int = 40) -> list[float]:
    """Deterministik trendli kapanış serisi."""
    return [round(base * (1.0 + drift * i + 0.01 * math.sin(i / 5.0)), 4) for i in range(n)]


def test_engine_deterministic_and_available() -> None:
    from packages.data.providers.rotation import engine

    closes = {
        "BTC": _series(68_000, 0.004),
        "GLD": _series(2_350, 0.001),
        "XAG": _series(28, 0.0015),
        "TLT": _series(95, -0.001),
        "SPY": _series(530, 0.003),
        "HYG": _series(78, 0.0008),
        "LQD": _series(110, 0.0002),
        "DXY": _series(104, -0.0005),
        "OIL": _series(82, 0.0012),
    }
    r1 = engine.compute(closes)
    r2 = engine.compute(closes)
    assert r1.available is True
    assert 0.0 <= r1.score <= 100.0
    assert r1.direction in {"bullish", "bearish", "neutral"}
    assert r1.evidence
    # Deterministik
    assert r1.score == r2.score
    assert r1.primary_flow == r2.primary_flow


def test_engine_insufficient_data_unavailable() -> None:
    from packages.data.providers.rotation import engine

    # Yalnızca 2 seri ve kısa → UNAVAILABLE, mock yok, crash yok.
    r = engine.compute({"BTC": _series(68_000, 0.004, 10), "GLD": _series(2_350, 0.001, 10)})
    assert r.available is False
    assert r.error
    assert r.score == 50.0
    assert r.class_scores == []


def test_engine_identical_returns_guard() -> None:
    from packages.data.providers.rotation import engine

    # 9 varlık birebir aynı seri → identical_returns guard.
    flat = _series(100, 0.002)
    closes = {k: list(flat) for k in engine.ROTATION_SYMBOLS}
    r = engine.compute(closes)
    assert r.available is False
    assert r.error == "identical_returns_across_assets"


def test_provider_fixture_mode_ok() -> None:
    # conftest TEST_USE_MOCK=true → ohlcv fixture barları (260 bar).
    from packages.data.providers import rotation as rot

    rot.reset_provider_status()
    view = rot.get_rotation()
    assert view.status == "OK"
    assert view.verified is True
    assert view.source == "ohlcv_1d_rotation"
    assert 0.0 <= view.score <= 100.0
    status = rot.get_provider_status()
    assert status["rotation"]["status"] == "ok"


def test_consensus_drops_quantum_when_rotation_unavailable() -> None:
    from packages.consensus.engine import build as build_consensus
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    # Rotasyonu UNAVAILABLE'a zorla.
    snap.rotation.status = "UNAVAILABLE"
    cons = build_consensus("BTCUSD", snap, regime)
    module_names = {m.name for m in cons.modules}
    assert "quantum" not in module_names
    assert 0 <= cons.score <= 100
    # Kalan modüllerin ağırlığı 1.0'a redistribute edilmeli. Tolerans 1e-3:
    # ModuleScore.weight GÖSTERİM için 4 ondalığa yuvarlanır (skor matematiği
    # yuvarlanmamış wt ile hesaplanır, bkz. engine.build: c = s * wt). Aktif
    # weights dosyası 4-ondalıklı değerler taşıyınca (auto-apply üretimi, örn.
    # v1.10.0) yuvarlama toplamı 1.0'dan ±(modül_sayısı × 5e-5) sapabilir —
    # eski 1e-6 toleransı bu kozmetik yuvarlamada kırılıyordu (invariant
    # yuvarlama ÖNCESİ toplamda korunur).
    assert abs(sum(m.weight for m in cons.modules) - 1.0) < 1e-3
