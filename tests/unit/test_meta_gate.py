"""Y-5 — Meta-label kapısı testleri (SALT-GÖLGE).

- compute(): dominant×TF kovası bariyer-kalite skoru (yalnız AUTO kohort;
  MANUAL/EXCLUDED tarihçeye sızmaz); quality_score = (good−bad)/n.
- assess(): kanıtsız bileşen nötr (0); TAKE/SKIP eşiği; regime_brake eksi
  bileşen; az örnekli kova nötr barrier bileşeni; deterministik.
- record_shadow()+scorecard(): fingerprint join; selective yalnız TAKE>SKIP.
- Engine kablolama: açılış adayı → shadow=True hüküm raporu, boyut/karar
  DEĞİŞMEZ (uygulama flag'i yok); aday-değil (HOLD) → boş rapor.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import meta_gate as mg

_CFG = {"meta_gate": {
    "min_score": 0.0, "min_bucket_n": 3,
    "weights": {"ev": 1.0, "empirical": 1.0, "mistake": 1.0,
                "barrier_history": 1.0, "regime_brake": 0.5},
}}


@pytest.fixture(autouse=True)
def gate_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("META_GATE_PATH", str(tmp_path / "meta_gate.json"))
    monkeypatch.setenv("META_GATE_SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(mg, "_cache", {"mtime": None, "data": None})
    return tmp_path


def _out(module="touche", tf="4h", quality="clean_win", fingerprint="fp",
         data_verified=True, open_reason="auto", pnl=1.0):
    return SimpleNamespace(dominant_module=module, timeframe=tf,
                           fingerprint=fingerprint, data_verified=data_verified,
                           open_reason=open_reason, pnl=pnl, _q=quality)


@pytest.fixture
def patch_barrier(monkeypatch):
    from packages.learning import exit_forensics
    monkeypatch.setattr(exit_forensics, "barrier_label",
                        lambda o: {"barrier": "X", "quality": o._q})


# ── compute ──────────────────────────────────────────────────────────────────

def test_compute_bucket_quality_score(patch_barrier):
    outs = ([_out(quality="clean_win")] * 3          # good
            + [_out(quality="roundtrip_loss")] * 1)  # bad
    with threshold_override(_CFG):
        table = mg.compute(outcomes=outs)
    b = table["buckets"]["touche|4h"]
    assert b["n"] == 4 and b["good"] == 3 and b["bad"] == 1
    assert b["quality_score"] == round((3 - 1) / 4, 4)


def test_compute_excludes_non_auto(patch_barrier):
    manual = _out(fingerprint=None, data_verified=False, open_reason="owner_manual")
    with threshold_override(_CFG):
        table = mg.compute(outcomes=[manual] * 5)
    assert table["buckets"] == {}  # MANUAL/EXCLUDED tarihçeye sızmaz


def test_compute_persists_and_hot_read(patch_barrier):
    with threshold_override(_CFG):
        mg.compute(outcomes=[_out(quality="clean_win")] * 3)
        loaded = mg._load_table()
    assert loaded and "touche|4h" in loaded["buckets"]


# ── assess (sıcak yol, saf skor) ─────────────────────────────────────────────

def test_assess_neutral_when_no_evidence():
    with threshold_override(_CFG):
        r = mg.assess(dominant_module="touche", timeframe="4h", regime_label="NEUTRAL",
                      expected_value=None, p_win_empirical=None, mistake_action=None,
                      regime_braked=False)
    assert r["score"] == 0.0 and r["verdict"] == "TAKE"  # eşik 0.0 → 0 dahil
    assert all(v == 0.0 for v in r["components"].values())
    assert r["shadow"] is True


def test_assess_regime_brake_pushes_skip():
    with threshold_override(_CFG):
        r = mg.assess(dominant_module="touche", timeframe="4h", regime_label="OFFENSIVE",
                      expected_value=None, p_win_empirical=None, mistake_action=None,
                      regime_braked=True)
    assert r["components"]["regime_brake"] == -1.0
    assert r["score"] < 0.0 and r["verdict"] == "SKIP"


def test_assess_positive_evidence_takes():
    with threshold_override(_CFG):
        r = mg.assess(dominant_module="touche", timeframe="4h", regime_label="NEUTRAL",
                      expected_value=0.5, p_win_empirical=0.65, mistake_action="BOOST",
                      regime_braked=False)
    assert r["components"]["ev"] == 0.5
    assert r["components"]["mistake"] == 1.0
    assert r["score"] > 0.0 and r["verdict"] == "TAKE"


def test_assess_barrier_component_needs_min_bucket_n(patch_barrier):
    # 2 kayıt < min_bucket_n(3) → barrier bileşeni nötr kalır.
    with threshold_override(_CFG):
        mg.compute(outcomes=[_out(quality="clean_win")] * 2)
        mg._cache["mtime"] = None
        r = mg.assess(dominant_module="touche", timeframe="4h", regime_label="NEUTRAL",
                      expected_value=None, p_win_empirical=None, mistake_action=None,
                      regime_braked=False)
    assert r["components"]["barrier_history"] == 0.0
    assert r["bucket_n"] == 2


def test_assess_barrier_component_applies_when_mature(patch_barrier):
    with threshold_override(_CFG):
        mg.compute(outcomes=[_out(quality="clean_win")] * 4)
        mg._cache["mtime"] = None
        r = mg.assess(dominant_module="touche", timeframe="4h", regime_label="NEUTRAL",
                      expected_value=None, p_win_empirical=None, mistake_action=None,
                      regime_braked=False)
    assert r["components"]["barrier_history"] == 1.0  # tümü clean_win


def test_assess_deterministic():
    kw = dict(dominant_module="touche", timeframe="4h", regime_label="NEUTRAL",
              expected_value=0.3, p_win_empirical=0.6, mistake_action=None,
              regime_braked=False)
    with threshold_override(_CFG):
        assert mg.assess(**kw) == mg.assess(**kw)


# ── record_shadow + scorecard ────────────────────────────────────────────────

def test_scorecard_joins_and_flags_selective():
    with threshold_override(_CFG):
        mg.record_shadow("fp_take", {"verdict": "TAKE", "score": 0.5})
        mg.record_shadow("fp_skip", {"verdict": "SKIP", "score": -0.5})
        outs = [_out(fingerprint="fp_take", pnl=10.0),
                _out(fingerprint="fp_skip", pnl=-10.0)]
        card = mg.scorecard(outcomes=outs)
    assert card["by_verdict"]["TAKE"]["n"] == 1
    assert card["by_verdict"]["SKIP"]["n"] == 1
    assert card["selective"] is True


def test_scorecard_unmatched_counts_ungated():
    with threshold_override(_CFG):
        card = mg.scorecard(outcomes=[_out(fingerprint="never_gated")])
    assert card["unmatched"] == 1
    assert card["by_verdict"]["TAKE"]["n"] == 0


def test_record_shadow_noop_without_fingerprint():
    mg.record_shadow(None, {"verdict": "TAKE", "score": 0.1})
    assert not mg._shadow_path().exists()


# ── engine kablolama (SALT-GÖLGE) ────────────────────────────────────────────

def _decide(monkeypatch):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=85.0, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=85.0, weight=1.0, contribution=85.0)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    hold = RiskDecision(action="HOLD", reason="ok", evidence=[])

    def run():
        return dec.decide_for_symbol("BTCUSD", snap, regime, hold, equity_usd=100_000)
    return run


def test_engine_shadow_report_never_changes_size(monkeypatch):
    run = _decide(monkeypatch)
    with threshold_override(_CFG):
        d = run()
    if d.action in ("open_long", "open_short"):
        assert d.meta_gate_report.get("shadow") is True
        assert d.meta_gate_report.get("verdict") in ("TAKE", "SKIP")
        assert "meta_gate" not in d.blocked_by  # hüküm kararı bloklamaz
    else:
        assert d.meta_gate_report == {}  # aday değil → boş rapor


def test_viewmodel_shape():
    with threshold_override(_CFG):
        vm = mg.viewmodel()
    assert vm["shadow_only"] is True
    assert "scorecard" in vm and "buckets" in vm
    assert vm["status"] in ("OK", "NO_TABLE")
