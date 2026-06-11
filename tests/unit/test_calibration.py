"""G6 — Confidence calibration & RiskGate-bypass koruması.

Politika:
- Calibrated confidence hiçbir koşulda RiskGate'i bypass etmez.
- Az veri → identity (a=1, b=0); confidence_source="identity"/"insufficient".
- Yeterli veriyle fit edilir; bins + (a, b) endpoint'te döner.
- Sadece data_verified=True + predicted_confidence is not None trade'ler
  fit'e/bins'e girer.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("REBALANCE_STORE_PATH", str(tmp_path / "rebalance.json"))
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "weights_active.json"))
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "weights_out"))

    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.learning import calibration_store as cs
    importlib.reload(cs)
    return ps, cs


def _seed_with_confidence(ps, n_high_win: int, n_low_loss: int) -> None:
    """Yüksek confidence + win, düşük confidence + loss kayıtları seed."""
    state = ps.load()
    for i in range(n_high_win):
        state.recent_trades.append(
            ps.Trade(
                id=f"hw{i}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=80.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="TP_HIT",
                fingerprint="BTCUSD|NEUTRAL|bullish|S65|C|touche",
                data_verified=True,
                predicted_confidence=0.8,
                raw_confidence=0.8,
                confidence_source="identity",
            )
        )
    for j in range(n_low_loss):
        state.recent_trades.append(
            ps.Trade(
                id=f"ll{j}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=99.0,
                pnl_usd=-60.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="SL_HIT",
                fingerprint="BTCUSD|NEUTRAL|bearish|S35|C|touche",
                data_verified=True,
                predicted_confidence=0.2,
                raw_confidence=0.2,
                confidence_source="identity",
            )
        )
    ps.save(state)


def test_predict_calibrated_identity_default(fresh_env) -> None:
    _, cs = fresh_env
    out, source = cs.predict_calibrated(0.42)
    assert out == 0.42
    assert source == "identity"


def test_trainer_insufficient_below_min_samples(fresh_env) -> None:
    ps, cs = fresh_env
    _seed_with_confidence(ps, n_high_win=3, n_low_loss=3)
    from packages.learning import calibration_trainer as ct
    res = ct.train()
    assert res["status"] == "INSUFFICIENT"
    assert res["samples"] == 6
    # Identity store yazıldı:
    p = cs.load()
    assert p.status == "insufficient"
    assert p.a == 1.0 and p.b == 0.0


def test_trainer_fits_when_enough_samples(fresh_env) -> None:
    ps, cs = fresh_env
    _seed_with_confidence(ps, n_high_win=8, n_low_loss=8)
    from packages.learning import calibration_trainer as ct
    res = ct.train()
    assert res["status"] == "FITTED"
    assert res["samples"] == 16
    p = cs.load()
    assert p.status == "fitted"
    # Yüksek confidence kazançla pozitif korelasyon → a > 0.
    assert p.a > 0
    # Calibrated p > 0.5 yüksek raw için
    cal, src = cs.predict_calibrated(0.8)
    assert src == "fitted"
    assert cal > 0.5


def test_unverified_or_missing_predicted_excluded(fresh_env) -> None:
    ps, _ = fresh_env
    # 12 verified+predicted (yeterli) ama içine 5 unverified ekle
    _seed_with_confidence(ps, n_high_win=6, n_low_loss=6)
    state = ps.load()
    for k in range(5):
        state.recent_trades.append(
            ps.Trade(
                id=f"unv{k}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=10.0,
                opened_at="2026-06-11T00:00:00+00:00",
                closed_at="2026-06-11T01:00:00+00:00",
                close_reason="TP_HIT",
                fingerprint="x",
                data_verified=False,
                predicted_confidence=0.9,
            )
        )
    ps.save(state)
    from packages.learning import calibration_trainer as ct
    res = ct.train()
    assert res["samples"] == 12  # unverified ekiler atlandı


def test_decision_calibration_does_not_bypass_kill_switch(fresh_env) -> None:
    # KILL_SWITCH altında, calibrated confidence yüksek olsa bile blocked.
    from packages.consensus.engine import build as build_consensus
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_for_symbol
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    # Calibration store kasten "fitted" pozitif a ile şişirelim ki confidence yüksek olsun.
    _, cs = fresh_env
    cs.save(cs.CalibrationParams(a=3.0, b=0.0, samples=20, fitted_at="t", status="fitted"))

    kill = RiskDecision(action="KILL_SWITCH", reason="DQS low", evidence=["DQS"])
    d = decide_for_symbol("BTCUSD", snap, regime, kill)
    assert d.action == "blocked"
    assert d.size_multiplier == 0.0
    assert d.confidence == 0.0  # kill switch hard 0
    # consensus var ama trade yok:
    assert isinstance(build_consensus("BTCUSD", snap, regime).score, float)


def test_decision_calibration_does_not_bypass_risk_reduce(fresh_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_for_symbol
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    _, cs = fresh_env
    cs.save(cs.CalibrationParams(a=3.0, b=0.0, samples=20, fitted_at="t", status="fitted"))

    rr = RiskDecision(action="RISK_REDUCE", reason="DD", evidence=[])
    d = decide_for_symbol("BTCUSD", snap, regime, rr)
    assert d.action == "hold"
    assert d.size_multiplier == 0.0


def test_decision_carries_calibration_source(fresh_env) -> None:
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision.engine import decide_for_symbol
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = decide_for_symbol("BTCUSD", snap, regime, hold_risk)
    # raw confidence damgalandı:
    assert 0.0 <= d.raw_confidence <= 1.0
    assert d.confidence_source in {"identity", "fitted", "insufficient"}


def test_calibration_endpoint_returns_state(fresh_env) -> None:
    ps, cs = fresh_env
    _seed_with_confidence(ps, n_high_win=6, n_low_loss=6)
    from packages.learning import calibration_trainer as ct
    ct.train()

    # API fresh import etmemize gerek yok — env her çağrıda okunuyor.
    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/learning/calibration")
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["status"] == "fitted"
    assert body["samples_in_state"] == 12
    assert isinstance(body["bins"], list)


def test_calibration_retrain_endpoint(fresh_env) -> None:
    ps, _ = fresh_env
    _seed_with_confidence(ps, n_high_win=6, n_low_loss=6)
    from apps.api.main import app

    client = TestClient(app)
    r = client.post("/api/v1/learning/calibration/retrain")
    assert r.status_code == 200
    assert r.json()["status"] == "FITTED"


def test_dqs_blocked_keeps_no_trade_even_with_high_confidence(
    fresh_env, monkeypatch
) -> None:
    """DATA_POLICY: DQS BLOCKED → trade yok; calibration yüksek olsa bile."""
    _, cs = fresh_env
    cs.save(cs.CalibrationParams(a=3.0, b=0.0, samples=20, fitted_at="t", status="fitted"))

    # Live provider'ları sustur → DATA_UNAVAILABLE → DQS BLOCKED → KILL_SWITCH
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    from packages.data.providers import price
    price.reset_provider_status()
    monkeypatch.setattr(price.coingecko, "get_quote", lambda s: None)
    monkeypatch.setattr(price.yfinance, "get_quote", lambda s: None)
    monkeypatch.setattr(price.fred, "get_quote", lambda s: None)

    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    snap = pl.build_snapshot(["BTCUSD"])
    assert snap.quality.status == "BLOCKED"

    from packages.decision.engine import decide_all
    from packages.risk.engine import RiskInput
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )
    _, risk, decisions = decide_all(["BTCUSD"], snap, risk_in)
    assert risk.action == "KILL_SWITCH"
    for d in decisions:
        assert d.action == "blocked"
        assert d.size_multiplier == 0.0
