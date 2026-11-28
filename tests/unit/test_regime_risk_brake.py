"""Y-1 — Rejim risk freni testleri.

- compute(): fren AUTO kohortun ortalama net R'si < 0 ve en az min_live_n R'li işlem
  varken (26 Kasım 2026, L2 + L6); az örnek fren yapmaz; guardrail [floor, 1.0];
  sonuç öneri dosyasına yazılır.
- active_mult(): canlı tablo yok/rejim frenli değil → (1.0, None); kurcalanmış
  mult > 1.0 okurken 1.0'a kırpılır (fren asla büyütmez).
- Engine kablolama: boyut × mult, blocked_by'da regime_risk_brake, rapor kanıtı taşır.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning import regime_risk_brake as rrb

_CFG = {"regime_risk_brake": {"min_live_n": 3, "brake_mult": 0.6, "floor": 0.4}}


@pytest.fixture(autouse=True)
def brake_path(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_RISK_BRAKE_PATH", str(tmp_path / "brake.json"))
    # mtime-cache path değişimini görmez — testler arası sızıntıyı kes.
    monkeypatch.setattr(rrb, "_cache", {"mtime": None, "data": None})
    return tmp_path


def _outcome(regime="OFFENSIVE", pnl=-10.0, net_r=None):
    # cohorts.classify AUTO şartı: fingerprint + data_verified. net_r: maliyet sonrası R.
    return SimpleNamespace(fingerprint="fp", data_verified=True, open_reason="auto",
                           regime=regime, pnl=pnl, net_pnl=pnl,
                           net_r=(net_r if net_r is not None else (-0.5 if pnl < 0 else 0.5)))


# ── compute ──────────────────────────────────────────────────────────────────

def test_compute_brakes_on_negative_net_r():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=-5.0)] * 4,
        )
    row = rep["per_regime"]["OFFENSIVE"]
    assert row["braked"] is True and row["mult"] == 0.6
    assert rep["braked_regimes"] == ["OFFENSIVE"]


def test_compute_no_brake_if_net_r_positive():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=+5.0)] * 4,
        )
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is False
    assert rep["per_regime"]["OFFENSIVE"]["mult"] == 1.0


def test_compute_no_brake_below_min_samples():
    with threshold_override(_CFG):
        rep = rrb.compute(
            outcomes=[_outcome(pnl=-5.0)] * 2,          # min_live_n=3 altı
        )
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is False


def test_compute_non_auto_outcomes_excluded():
    # fingerprint'siz (AUTO dışı) kayıtlar kanıta girmez → fren yok.
    manual = SimpleNamespace(fingerprint=None, data_verified=True,
                             open_reason="owner_manual", regime="OFFENSIVE", pnl=-50.0)
    with threshold_override(_CFG):
        rep = rrb.compute(outcomes=[manual] * 10)
    assert "OFFENSIVE" not in rep["per_regime"]  # kanıt yok → satır yok, fren yok


def test_compute_floor_guardrail():
    cfg = {"regime_risk_brake": {**_CFG["regime_risk_brake"],
                                 "brake_mult": 0.1, "floor": 0.4}}
    with threshold_override(cfg):
        rep = rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4)
    assert rep["per_regime"]["OFFENSIVE"]["mult"] == 0.4  # taban: kısma, kapatma değil


def _approve(mod) -> None:
    """Owner onayı: öneri dosyası canlıya kopyalanır (26 Kasım 2026'dan beri canlı tablo
    kendiliğinden değişmez)."""
    live = mod._store_path() if hasattr(mod, "_store_path") else mod._path()
    live.write_text(mod._proposal_path().read_text(encoding="utf-8"), encoding="utf-8")
    if hasattr(mod, "_cache"):
        mod._cache["mtime"] = None


# ── active_mult (sıcak yol) ──────────────────────────────────────────────────

def test_active_mult_reads_braked_regime():
    with threshold_override(_CFG):
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4)
        assert rrb.active_mult("OFFENSIVE") == (1.0, None)  # canlı tablo kendiliğinden değişmez
        _approve(rrb)
        mult, ev = rrb.active_mult("OFFENSIVE")
        assert mult == 0.6 and ev is not None and ev["regime"] == "OFFENSIVE"
        assert rrb.active_mult("NEUTRAL") == (1.0, None)   # frensiz rejim


def test_active_mult_missing_and_old_table():
    with threshold_override(_CFG):
        assert rrb.active_mult("OFFENSIVE") == (1.0, None)  # tablo yok
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4,
                    now=datetime.now(UTC) - timedelta(hours=72))
        _approve(rrb)
        # Donmuş canlı tablo yaşı yüzünden düşmez (eskiden 48 saatte fren kalkıyordu).
        assert rrb.active_mult("OFFENSIVE")[0] == 0.6


def test_active_mult_never_boosts_on_tampered_artifact():
    with threshold_override(_CFG):
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4)
        _approve(rrb)
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
    rrb._path().parent.mkdir(parents=True, exist_ok=True)
    rrb._path().write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(),
        "per_regime": {regime_label.upper(): {
            "mult": mult, "braked": True,
            "evidence": {"live": {"n": 4}, "backtest": {"n": 6}},
        }},
        "braked_regimes": [regime_label.upper()],
    }), encoding="utf-8")
    rrb._cache["mtime"] = None


def test_engine_reduces_size(monkeypatch):
    run, regime = _decide(monkeypatch)
    with threshold_override(_CFG):
        base = run()
    _write_brake_for(regime.label, mult=0.5)
    with threshold_override(_CFG):
        on = run()
    assert on.size_multiplier == pytest.approx(base.size_multiplier * 0.5, abs=1e-3)
    assert on.regime_brake_report
    assert "regime_risk_brake" in on.blocked_by


def test_brake_uses_net_r_not_usd_sum():
    """USD toplamı pozitif olsa da ortalama net R negatifse fren (boyuttan bağımsız)."""
    outs = [_outcome(pnl=+50.0, net_r=-0.2)] * 3 + [_outcome(pnl=-1.0, net_r=-0.1)]
    with threshold_override(_CFG):
        rep = rrb.compute(outcomes=outs)
    live = rep["per_regime"]["OFFENSIVE"]["evidence"]["live"]
    assert rep["per_regime"]["OFFENSIVE"]["braked"] is True
    assert live["mean_net_r"] == -0.175 and live["n"] == 4


def test_compute_writes_proposal_not_live():
    with threshold_override(_CFG):
        rrb.compute(outcomes=[_outcome(pnl=-5.0)] * 4)
    assert rrb._proposal_path().exists() and not rrb._path().exists()
