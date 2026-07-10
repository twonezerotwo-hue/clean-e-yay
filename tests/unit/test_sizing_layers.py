"""Boyut katmanları testleri (P1): inanç-boyu + oynaklık-paritesi.

Kritik güvenceler:
- NO-BOOST: hiçbir faktör asla >1.0 (boyut ARTMAZ).
- Shadow-first: iki flag de kapalıyken applied_factor == 1.0 (boyut bayt-aynı).
- Saf/defansif: geçersiz/yetersiz girdi → 1.0 (kısma yok, uydurma yok).
"""
from __future__ import annotations

import importlib

import pytest

from packages.decision import sizing_layers as sl


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _force_pass(monkeypatch, *, score=85.0):
    """Consensus'u sabitle → aday açılışa kadar geçer (concentration test deseni)."""
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=score, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=score, weight=1.0, contribution=score)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    return dec, snap, regime


def test_conviction_at_threshold_is_min_factor():
    """Eşiğe yakın (zayıf) sinyal → min_factor. score=65, eşik-uzaklığı 15 → strength 15."""
    f = sl.conviction_factor(65.0, threshold_dist=15.0, full_strength=25.0, min_factor=0.5)
    assert abs(f - 0.5) < 1e-9


def test_conviction_at_full_strength_is_one():
    """Tam güçte (strength ≥ full_strength) → 1.0."""
    f = sl.conviction_factor(75.0, threshold_dist=15.0, full_strength=25.0, min_factor=0.5)
    assert abs(f - 1.0) < 1e-9


def test_conviction_midpoint_interpolates():
    """Eşik (15) ile tam-güç (25) ortası (strength 20) → min ile 1.0 arası (0.75)."""
    f = sl.conviction_factor(70.0, threshold_dist=15.0, full_strength=25.0, min_factor=0.5)
    assert abs(f - 0.75) < 1e-9


def test_conviction_never_boosts():
    """Aşırı güçlü sinyal bile faktörü 1.0'ın üstüne çıkaramaz (no-boost)."""
    f = sl.conviction_factor(100.0, threshold_dist=15.0, full_strength=25.0, min_factor=0.5)
    assert f == 1.0


def test_conviction_short_side_symmetric():
    """Short tarafı ayna: score=35 (nötrden 15 uzak) → eşikte min_factor."""
    f = sl.conviction_factor(35.0, threshold_dist=15.0, full_strength=25.0, min_factor=0.5)
    assert abs(f - 0.5) < 1e-9


def test_conviction_degenerate_span_is_one():
    """full_strength ≤ threshold_dist (bozuk config) → güvenli 1.0 (kısma yok)."""
    assert sl.conviction_factor(80.0, threshold_dist=25.0, full_strength=25.0, min_factor=0.5) == 1.0


def test_vol_parity_below_ref_is_one():
    """Oynaklık referans altında → 1.0 (büyütme YOK, no-boost)."""
    assert sl.vol_parity_factor(0.02, ref_vol=0.03, floor=0.3) == 1.0


def test_vol_parity_above_ref_reduces():
    """Oynaklık referansın 2 katı → yarı boyut (ref/realized)."""
    f = sl.vol_parity_factor(0.06, ref_vol=0.03, floor=0.3)
    assert abs(f - 0.5) < 1e-9


def test_vol_parity_floor_clamps():
    """Çok oynak varlık floor'a takılır (aşırı kısma engellenir)."""
    f = sl.vol_parity_factor(1.0, ref_vol=0.03, floor=0.3)
    assert abs(f - 0.3) < 1e-9


def test_vol_parity_invalid_is_one():
    """Geçersiz/eksik oynaklık → 1.0 (kısma yok)."""
    assert sl.vol_parity_factor(0.0, ref_vol=0.03, floor=0.3) == 1.0
    assert sl.vol_parity_factor(None, ref_vol=0.03, floor=0.3) == 1.0


def test_evaluate_shadow_both_off_is_byte_identical():
    """İKİ flag de kapalı → applied_factor 1.0 (rapor dolu ama boyut bayt-aynı)."""
    r = sl.evaluate(
        score=80.0, realized_vol=0.10, threshold_dist=15.0,
        conviction_cfg={"enabled": False}, vol_parity_cfg={"enabled": False},
    )
    assert r["applied_factor"] == 1.0
    assert r["conviction"]["enabled"] is False and r["vol_parity"]["enabled"] is False
    # rapor faktörleri yine de hesaplanmış (shadow gözlem)
    assert r["conviction"]["factor"] == 1.0          # score 80 zaten tam güç
    assert r["vol_parity"]["factor"] < 1.0           # 0.10 > ref 0.03 → kısacaktı


def test_evaluate_conviction_only_applies():
    """Yalnız inanç açık → yalnız o faktör uygulanır."""
    r = sl.evaluate(
        score=65.0, realized_vol=0.10, threshold_dist=15.0,
        conviction_cfg={"enabled": True, "full_strength": 25.0, "min_factor": 0.5},
        vol_parity_cfg={"enabled": False},
    )
    assert abs(r["applied_factor"] - 0.5) < 1e-9      # sadece conviction (0.5)


def test_evaluate_both_on_multiplies_and_clamps():
    """İkisi de açık → çarpım, ve asla >1.0 (no-boost güvencesi)."""
    r = sl.evaluate(
        score=100.0, realized_vol=0.01, threshold_dist=15.0,   # ikisi de 1.0 verir
        conviction_cfg={"enabled": True, "full_strength": 25.0, "min_factor": 0.5},
        vol_parity_cfg={"enabled": True, "ref_vol": 0.03, "floor": 0.3},
    )
    assert r["applied_factor"] == 1.0                # 1.0 × 1.0, boost yok


def test_evaluate_never_exceeds_one():
    """Her kombinasyonda applied_factor ∈ [0,1] (no-boost invariant)."""
    for score in (55.0, 70.0, 90.0):
        for rv in (0.005, 0.03, 0.2):
            r = sl.evaluate(
                score=score, realized_vol=rv, threshold_dist=15.0,
                conviction_cfg={"enabled": True, "full_strength": 25.0, "min_factor": 0.5},
                vol_parity_cfg={"enabled": True, "ref_vol": 0.03, "floor": 0.3},
            )
            assert 0.0 <= r["applied_factor"] <= 1.0


# ---------------- engine entegrasyonu (end-to-end) ----------------

def test_engine_shadow_default_byte_identical(fresh_env, monkeypatch):
    """Default (iki flag kapalı): rapor DOLU ama boyut/aksiyon BAYT-AYNI (shadow)."""
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force_pass(monkeypatch)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, equity_usd=100_000)
    assert d.action == "open_long"
    assert d.sizing_layers_report  # rapor her kararda hesaplanır (gölge gözlem)
    assert d.sizing_layers_report["applied_factor"] == 1.0
    assert "sizing_layers" not in d.blocked_by
    assert d.size_multiplier > 0.0


def test_engine_conviction_on_reduces_size(fresh_env, monkeypatch):
    """İnanç açık + zayıf-ish sinyal (full_strength yüksek) → boyut KISILIR, yön korunur."""
    from packages.risk.engine import RiskDecision
    dec, snap, regime = _force_pass(monkeypatch, score=85.0)
    # full_strength çok yüksek (100) → güçlü sinyal (strength 35) bile tam-güce
    # ulaşmaz → faktör <1.0 (kontrollü kısma; gerçek config 25 civarı).
    monkeypatch.setattr(dec, "_sizing_layers_cfg", lambda: {
        "conviction": {"enabled": True, "full_strength": 100.0, "min_factor": 0.5},
        "vol_parity": {"enabled": False},
    })
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk, equity_usd=100_000)
    assert d.action == "open_long"                    # yalnız kısar, yön çevirmez
    assert d.sizing_layers_report["applied_factor"] < 1.0
    assert d.sizing_layers_report["conviction"]["enabled"] is True
    assert "sizing_layers" in d.blocked_by
    assert d.size_multiplier > 0.0                    # kısar ama sıfırlamaz
