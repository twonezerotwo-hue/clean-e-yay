"""G4 — Correlation-aware sizing testleri.

- Veri yetersiz + baseline'da olmayan çift → neutral (rho=0, adjustment yok,
  insufficient_correlation_data uyarısı).
- Baseline çifti (BTC↔ETH) config'ten okunur.
- Yeterli ortak gün varsa rho trade PnL serisinden hesaplanır (computed).
- Aynı yön + yüksek korelasyon → cluster cap: yarıyı aşınca size×0.5,
  cap'i aşınca hold (size 0).
- Ters yön → hedge: cap'e girmez, size küçülmez.
- **RiskGate bypass yok**: KILL_SWITCH/DQS BLOCKED correlation'dan önce.
- Endpoint matris + cluster döner. Hepsi offline (mock paper state seed).
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
    return ps


def _position(ps, *, symbol: str, side: str, size_usd: float, pid: str = "p1"):
    return ps.Position(
        id=pid,
        symbol=symbol,
        side=side,
        entry_price=100.0,
        current_price=100.0,
        size_usd=size_usd,
        sl=None,
        tp=None,
        opened_at="2026-06-11T00:00:00+00:00",
    )


def _seed_pnl(ps, symbol: str, day_pnls: list[tuple[str, float]]) -> None:
    """Verified kapalı trade'ler — korelasyon serisi için."""
    state = ps.load()
    for i, (day, pnl) in enumerate(day_pnls):
        state.recent_trades.append(
            ps.Trade(
                id=f"{symbol}-{i}",
                symbol=symbol,
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=pnl,
                opened_at=f"{day}T00:00:00+00:00",
                closed_at=f"{day}T01:00:00+00:00",
                close_reason="TP_HIT",
                data_verified=True,
            )
        )
    ps.save(state)


# ---------------- pair correlation fallback sırası ----------------

def test_unknown_pair_is_neutral(fresh_env) -> None:
    from packages.risk import correlation as corr
    e = corr.pair_correlation("BTCUSD", "XAUUSD", {})
    assert e.source == "neutral"
    assert e.rho == 0.0


def test_baseline_pair_from_config(fresh_env) -> None:
    from packages.risk import correlation as corr
    e = corr.pair_correlation("BTCUSD", "ETHUSD", {})
    assert e.source == "baseline"
    assert e.rho == 0.75
    # Simetrik okuma
    e2 = corr.pair_correlation("ETHUSD", "BTCUSD", {})
    assert e2.rho == 0.75


def test_computed_rho_from_verified_trades(fresh_env) -> None:
    from packages.risk import correlation as corr
    ps = fresh_env
    days = [f"2026-06-{d:02d}" for d in range(1, 8)]  # 7 ortak gün ≥ 5
    _seed_pnl(ps, "BTCUSD", [(d, float(i - 3) * 10) for i, d in enumerate(days)])
    _seed_pnl(ps, "ETHUSD", [(d, float(i - 3) * 7) for i, d in enumerate(days)])
    series = corr.daily_pnl_series(ps.load().recent_trades)
    e = corr.pair_correlation("BTCUSD", "ETHUSD", series)
    assert e.source == "computed"
    assert e.samples == 7
    assert e.rho == pytest.approx(1.0, abs=0.01)


def test_unverified_trades_excluded_from_series(fresh_env) -> None:
    from packages.risk import correlation as corr
    ps = fresh_env
    state = ps.load()
    state.recent_trades.append(
        ps.Trade(
            id="x", symbol="BTCUSD", side="long", entry_price=100.0,
            exit_price=101.0, pnl_usd=10.0,
            opened_at="2026-06-01T00:00:00+00:00",
            closed_at="2026-06-01T01:00:00+00:00",
            close_reason="TP_HIT", data_verified=False,
        )
    )
    ps.save(state)
    assert corr.daily_pnl_series(ps.load().recent_trades) == {}


# ---------------- cluster exposure ----------------

def test_cluster_same_direction_reduced_then_capped(fresh_env) -> None:
    from packages.risk import correlation as corr
    ps = fresh_env
    # ETH long 20k / 100k equity → cluster %20 ∈ [%15, %30) → REDUCED (×0.5)
    pos = _position(ps, symbol="ETHUSD", side="long", size_usd=20_000)
    rep = corr.cluster_exposure([pos], "BTCUSD", "long", 100_000)
    assert rep.status == "REDUCED"
    assert rep.size_factor == 0.5
    assert rep.cluster_pct == pytest.approx(0.20)
    assert len(rep.members) == 1

    # ETH long 31k → %31 ≥ cap %30 → CAPPED (×0)
    pos_big = _position(ps, symbol="ETHUSD", side="long", size_usd=31_000)
    rep2 = corr.cluster_exposure([pos_big], "BTCUSD", "long", 100_000)
    assert rep2.status == "CAPPED"
    assert rep2.size_factor == 0.0


def test_cluster_opposite_direction_is_hedge(fresh_env) -> None:
    from packages.risk import correlation as corr
    ps = fresh_env
    # ETH short, aday BTC long, rho=+0.75 → hizalama -0.75 → hedge, cap yok
    pos = _position(ps, symbol="ETHUSD", side="short", size_usd=40_000)
    rep = corr.cluster_exposure([pos], "BTCUSD", "long", 100_000)
    assert rep.status == "OK"
    assert rep.size_factor == 1.0
    assert rep.members == []
    assert len(rep.hedges) == 1


def test_cluster_insufficient_pair_neutral_no_adjustment(fresh_env) -> None:
    from packages.risk import correlation as corr
    ps = fresh_env
    # BTC↔XAU baseline'da yok → neutral; büyük pozisyona rağmen factor 1.0
    pos = _position(ps, symbol="XAUUSD", side="long", size_usd=90_000)
    rep = corr.cluster_exposure([pos], "BTCUSD", "long", 100_000)
    assert rep.size_factor == 1.0
    assert rep.members == []
    assert any(w.startswith("insufficient_correlation_data:") for w in rep.warnings)


def test_cluster_never_increases_size_factor(fresh_env) -> None:
    from packages.risk import correlation as corr
    rep = corr.cluster_exposure([], "BTCUSD", "long", 100_000)
    assert rep.size_factor <= 1.0


# ---------------- decision engine wiring ----------------

def _force_decision_pass(monkeypatch):
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    return snap, regime


def _force_strong_bullish(monkeypatch, dec_module):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    fake = ConsensusResult(
        symbol="BTCUSD",
        score=85.0,
        direction="bullish",
        confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=85.0, weight=1.0, contribution=85.0)],
    )
    monkeypatch.setattr(dec_module, "build_consensus", lambda *a, **kw: fake)


def test_decision_correlation_cap_returns_hold(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision

    snap, regime = _force_decision_pass(monkeypatch)
    _force_strong_bullish(monkeypatch, dec)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    pos = _position(fresh_env, symbol="ETHUSD", side="long", size_usd=35_000)

    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk,
        open_positions=[pos], equity_usd=100_000,
    )
    assert d.action == "hold"
    assert d.size_multiplier == 0.0
    assert "correlation_cluster" in d.reason
    assert d.cluster_report.get("status") == "CAPPED"


def test_decision_correlation_reduces_size(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision

    snap, regime = _force_decision_pass(monkeypatch)
    _force_strong_bullish(monkeypatch, dec)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    base = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[], equity_usd=100_000
    )
    assert base.action == "open_long"

    pos = _position(fresh_env, symbol="ETHUSD", side="long", size_usd=20_000)
    reduced = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk,
        open_positions=[pos], equity_usd=100_000,
    )
    assert reduced.action == "open_long"
    assert reduced.size_multiplier == pytest.approx(base.size_multiplier * 0.5)
    assert reduced.cluster_report.get("status") == "REDUCED"


def test_decision_hedge_keeps_full_size(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision

    snap, regime = _force_decision_pass(monkeypatch)
    _force_strong_bullish(monkeypatch, dec)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    base = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[], equity_usd=100_000
    )
    pos = _position(fresh_env, symbol="ETHUSD", side="short", size_usd=35_000)
    hedged = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk,
        open_positions=[pos], equity_usd=100_000,
    )
    assert hedged.action == "open_long"
    assert hedged.size_multiplier == base.size_multiplier
    assert len(hedged.cluster_report.get("hedges", [])) == 1


def test_kill_switch_beats_correlation(fresh_env, monkeypatch) -> None:
    """KILL_SWITCH her zaman önce — correlation hesabına hiç gelinmez."""
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision

    snap, regime = _force_decision_pass(monkeypatch)
    _force_strong_bullish(monkeypatch, dec)
    kill = RiskDecision(action="KILL_SWITCH", reason="DQS", evidence=[])

    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, kill, open_positions=[], equity_usd=100_000
    )
    assert d.action == "blocked"
    assert d.size_multiplier == 0.0
    assert d.cluster_report == {}


def test_dqs_blocked_no_trade_with_open_positions(fresh_env, monkeypatch) -> None:
    """DQS BLOCKED → KILL_SWITCH → blocked; correlation devreye girmez."""
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    from packages.data.providers import price
    price.reset_provider_status()
    monkeypatch.setattr(price.coingecko, "get_quote", lambda s: None)
    monkeypatch.setattr(price.yfinance, "get_quote", lambda s: None)
    monkeypatch.setattr(price.fred, "get_quote", lambda s: None)
    monkeypatch.setattr(price.twelvedata, "get_quote", lambda s: None)
    monkeypatch.setattr(price.alphavantage, "get_quote", lambda s: None)
    monkeypatch.setattr(price.finnhub, "get_quote", lambda s: None)

    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    snap = pl.build_snapshot(["BTCUSD"])
    assert snap.quality.status == "BLOCKED"

    from packages.decision import engine as dec
    from packages.risk.engine import RiskInput

    pos = _position(fresh_env, symbol="ETHUSD", side="long", size_usd=20_000)
    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=1,
    )
    _, risk, decisions = dec.decide_all(
        ["BTCUSD"], snap, risk_in, open_positions=[pos]
    )
    assert risk.action == "KILL_SWITCH"
    for d in decisions:
        assert d.action == "blocked"
        assert d.size_multiplier == 0.0


# ---------------- endpoint ----------------

def test_correlation_endpoint(fresh_env) -> None:
    ps = fresh_env
    state = ps.load()
    state.open_positions.append(
        _position(ps, symbol="BTCUSD", side="long", size_usd=15_000, pid="b1")
    )
    state.open_positions.append(
        _position(ps, symbol="ETHUSD", side="long", size_usd=20_000, pid="e1")
    )
    ps.save(state)

    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/risk/correlation")
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] == 0.7
    assert body["max_cluster_pct"] == 0.30
    assert {"BTCUSD", "ETHUSD"} <= set(body["symbols"])
    assert body["matrix"]
    # BTC long + ETH long rho 0.75 → tek cluster, 35k / 100k → BREACH
    assert body["clusters"]
    top = body["clusters"][0]
    assert set(top["symbols"]) == {"BTCUSD", "ETHUSD"}
    assert top["cluster_pct"] == pytest.approx(0.35)
    assert top["status"] == "BREACH"


def test_ev_gate_blocks_negative_ev(fresh_env, monkeypatch) -> None:
    # F5: ev_gate AÇIK + skor açılır (62→cal_conf 0.24, floor'u geçer) ama EV negatif
    # (0.24×2.5 − 0.76 − 0.1 = −0.26) → hold (blocked_by ev_gate).
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision

    snap, regime = _force_decision_pass(monkeypatch)
    fake = ConsensusResult(
        symbol="BTCUSD", score=62.0, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=62.0, weight=1.0, contribution=62.0)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    # autouse fixture ev_gate'i kapatmıştı — bu testte AÇ (1d → RR 2.5).
    monkeypatch.setattr(dec, "_ev_gate_cfg", lambda: {"enabled": True, "min_ev": 0.0, "cost_r": 0.1})
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])
    d = dec.decide_for_symbol(
        "BTCUSD", snap, regime, hold_risk, open_positions=[], equity_usd=100_000, timeframe="1d"
    )
    assert d.action == "hold"
    assert "ev_gate" in d.blocked_by
    assert d.expected_value is not None and d.expected_value < 0
