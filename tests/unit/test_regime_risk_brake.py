"""Y-1 — Rejim risk freni testleri.

- compute(): fren YALNIZ çift-negatif kanıtta (canlı AUTO kohort + backtest
  challenger, ikisi de min örnek + negatif); tek kaynak/az örnek fren yapmaz;
  guardrail [floor, 1.0].
- active_mult(): artifact yok/bayat/rejim frenli değil → (1.0, None); kurcalanmış
  mult > 1.0 okurken 1.0'a kırpılır (fren asla büyütmez).
- Engine kablolama: flag OFF → boyut bayt-aynı + shadow raporu applied=False;
  flag ON → boyut × mult, blocked_by'da regime_risk_brake.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import regime_risk_brake as rrb

_CFG = {"regime_risk_brake": {
    "enabled": False, "min_live_n": 3, "min_backtest_n": 5,
    "brake_mult": 0.6, "floor": 0.4, "max_age_hours": 48,
}}


@pytest.fixture(autouse=True)
def brake_path(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_RISK_BRAKE_PATH", str(tmp_path / "brake.json"))
    # mtime-cache path değişimini görmez — testler arası sızıntıyı kes.
    monkeypatch.setattr(rrb, "_cache", {"mtime": None, "data": None})
    return tmp_path


def _outcome(regime="OFFENSIVE", pnl=-10.0):
    # cohorts.classify AUTO şartı: fingerprint + data_verified.
    return SimpleNamespace(fingerprint="fp", data_verified=True,
                           open_reason="auto", regime=regime, pnl=pnl)


def _bt(regime="OFFENSIVE", dr=-0.01, direction="bullish"):
    return {"regime_label": regime, "direction": direction, "directional_return": dr}


# ── compute ──────────────────────────────────────────────────────────────────

def test_compute_brakes_only_on_double_negative():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=-5.0)] * 4,
            challenger_records=[_bt(dr=-0.02)] * 6,
        )
    row = rep["per_regime"]["OFFENSIVE"]
    assert row["braked"] is True and row["mult"] == 0.6
    assert rep["braked_regimes"] == ["OFFENSIVE"]


def test_compute_no_brake_if_live_positive():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=+5.0)] * 4,
            challenger_records=[_bt(dr=-0.02)] * 6,
        )
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is False
    assert rep["per_regime"]["OFFENSIVE"]["mult"] == 1.0


def test_compute_no_brake_below_min_samples():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=-5.0)] * 2,          # min_live_n=3 altı
            challenger_records=[_bt(dr=-0.02)] * 6,
        )
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is False


def test_compute_non_auto_outcomes_excluded():
    # fingerprint'siz (AUTO dışı) kayıtlar kanıta girmez → fren yok.
    manual = SimpleNamespace(fingerprint=None, data_verified=True,
                             open_reason="owner_manual", regime="OFFENSIVE", pnl=-50.0)
    with threshold_override(_CFG):
        rep = rrb.compute(outcomes=[manual] * 10,
                          challenger_records=[_bt(dr=-0.02)] * 6)
    assert rep["per_regime"]["OFFENSIVE"]["evidence"]["live"]["n"] == 0
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is False


def test_compute_floor_guardrail():
    cfg = {"regime_risk_brake": {**_CFG["regime_risk_brake"],
                                 "brake_mult": 0.1, "floor": 0.4}}
    with threshold_override(cfg):
        rep = rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4,
                          challenger_records=[_bt(dr=-0.02)] * 6)
    assert rep["per_regime"]["OFFENSIVE"]["mult"] == 0.4  # taban: kısma, kapatma değil


# ── active_mult (sıcak yol) ──────────────────────────────────────────────────

def test_active_mult_reads_braked_regime():
    with threshold_override(_CFG):
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4,
                    challenger_records=[_bt(dr=-0.02)] * 6)
        mult, ev = rrb.active_mult("OFFENSIVE")
        assert mult == 0.6 and ev is not None and ev["regime"] == "OFFENSIVE"
        assert rrb.active_mult("NEUTRAL") == (1.0, None)   # frensiz rejim


def test_active_mult_missing_and_stale_artifact():
    with threshold_override(_CFG):
        assert rrb.active_mult("OFFENSIVE") == (1.0, None)  # artifact yok
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4,
                    challenger_records=[_bt(dr=-0.02)] * 6,
                    now=datetime.now(UTC) - timedelta(hours=72))
        # 48h'ten yaşlı → fren düşer (öğrenme durmuş, uydurma fren yok).
        assert rrb.active_mult("OFFENSIVE") == (1.0, None)


def test_active_mult_never_boosts_on_tampered_artifact():
    with threshold_override(_CFG):
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4,
                    challenger_records=[_bt(dr=-0.02)] * 6)
        p = rrb._path()
        data = json.loads(p.read_text(encoding="utf-8"))
        data["per_regime"]["OFFENSIVE"]["mult"] = 1.7   # bozuk/kurcalanmış değer
        p.write_text(json.dumps(data), encoding="utf-8")
        rrb._cache["mtime"] = None
        mult, _ = rrb.active_mult("OFFENSIVE")
        assert mult == 1.0  # no-boost invariant okurken de geçerli


# ── engine kablolama (end-to-end) ────────────────────────────────────────────

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
    return run, regime


def _write_brake_for(regime_label: str, mult: float = 0.5):
    rrb._write({
        "generated_at": datetime.now(UTC).isoformat(),
        "per_regime": {regime_label.upper(): {
            "mult": mult, "braked": True,
            "evidence": {"live": {"n": 4}, "backtest": {"n": 6}},
        }},
        "braked_regimes": [regime_label.upper()],
    })
    rrb._cache["mtime"] = None


def test_engine_flag_off_byte_same_with_shadow(monkeypatch):
    run, regime = _decide(monkeypatch)
    with threshold_override(_CFG):
        base = run()
        assert base.size_multiplier > 0
        assert base.regime_brake_report == {}          # kanıt yok → boş
        _write_brake_for(regime.label, mult=0.5)
        off = run()
        assert off.size_multiplier == base.size_multiplier  # bayt-aynı boyut
        assert off.regime_brake_report.get("applied") is False  # shadow birikir
        assert "regime_risk_brake" not in off.blocked_by


def test_engine_flag_on_reduces_size(monkeypatch):
    run, regime = _decide(monkeypatch)
    on_cfg = {"regime_risk_brake": {**_CFG["regime_risk_brake"], "enabled": True}}
    with threshold_override(_CFG):
        base = run()
    _write_brake_for(regime.label, mult=0.5)
    with threshold_override(on_cfg):
        on = run()
    assert on.size_multiplier == round(base.size_multiplier * 0.5, 3)
    assert on.regime_brake_report.get("applied") is True
    assert "regime_risk_brake" in on.blocked_by
