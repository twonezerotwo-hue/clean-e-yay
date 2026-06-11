"""G3 — Mistake memory gate testleri.

- summary() yalnızca data_verified=True + fingerprint'i olan trade'leri
  toplar.
- evaluate(): MIN_TRADES altında NEUTRAL; düşük win_rate → AVOID;
  yüksek → BOOST; streak ≥ STREAK_AVOID → AVOID.
- decision engine: AVOID → hold; BOOST → size+; WARNING → size-.
- **RiskGate bypass yok**: KILL_SWITCH/RISK_REDUCE yüksek BOOST'a rağmen
  blocked/hold.
- DQS BLOCKED + BOOST → trade yok.
- Endpoint kayıt + verdict listesi döner.
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


def _seed(ps, fp: str, wins: int, losses: int, *, last_n_losses: int = 0) -> None:
    """Seed verified trades with fingerprint fp.

    `last_n_losses` parametresi ile zaman sırasına göre son N'yi kayıp yapar
    (streak testi için).
    """
    state = ps.load()
    base_ts = "2026-06-11T00:{:02d}:00+00:00"
    idx = 0
    # Önce kazançlar
    for _ in range(wins):
        state.recent_trades.append(
            ps.Trade(
                id=f"w{idx}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=80.0,
                opened_at=base_ts.format(idx),
                closed_at=base_ts.format(idx),
                close_reason="TP_HIT",
                fingerprint=fp,
                data_verified=True,
                predicted_confidence=0.7,
                raw_confidence=0.7,
                confidence_source="identity",
            )
        )
        idx += 1
    # Sonra kayıplar
    for _ in range(losses):
        state.recent_trades.append(
            ps.Trade(
                id=f"l{idx}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=99.0,
                pnl_usd=-50.0,
                opened_at=base_ts.format(idx),
                closed_at=base_ts.format(idx),
                close_reason="SL_HIT",
                fingerprint=fp,
                data_verified=True,
                predicted_confidence=0.3,
                raw_confidence=0.3,
                confidence_source="identity",
            )
        )
        idx += 1
    ps.save(state)


# ---------------- summary / evaluate ----------------

def test_summary_skips_unverified_and_missing_fp(fresh_env) -> None:
    ps = fresh_env
    # Verified+fp olan 3 ve unverified 2 ekle
    _seed(ps, "FP-A", wins=2, losses=1)
    state = ps.load()
    state.recent_trades.append(
        ps.Trade(
            id="unv",
            symbol="BTCUSD",
            side="long",
            entry_price=100.0,
            exit_price=101.0,
            pnl_usd=10,
            opened_at="t",
            closed_at="t",
            close_reason="TP_HIT",
            fingerprint="FP-A",
            data_verified=False,
        )
    )
    state.recent_trades.append(
        ps.Trade(
            id="nofp",
            symbol="BTCUSD",
            side="long",
            entry_price=100.0,
            exit_price=101.0,
            pnl_usd=10,
            opened_at="t",
            closed_at="t",
            close_reason="TP_HIT",
            fingerprint=None,
            data_verified=True,
        )
    )
    ps.save(state)
    from packages.learning import mistake_memory as mm
    mems = mm.summary()
    assert len(mems) == 1
    assert mems[0].fingerprint == "FP-A"
    assert mems[0].trades == 3


def test_evaluate_neutral_below_min_trades(fresh_env) -> None:
    _seed(fresh_env, "FP-N", wins=1, losses=1)  # 2 < MIN_TRADES (3)
    from packages.learning import mistake_memory as mm
    v = mm.evaluate("FP-N")
    assert v.action == "NEUTRAL"
    assert v.size_factor == 1.0


def test_evaluate_avoid_low_win_rate(fresh_env) -> None:
    _seed(fresh_env, "FP-AVOID", wins=1, losses=5)  # win_rate ≈ 0.17 < 0.35
    from packages.learning import mistake_memory as mm
    v = mm.evaluate("FP-AVOID")
    assert v.action == "AVOID"
    assert v.size_factor == 0.0


def test_evaluate_boost_high_win_rate(fresh_env) -> None:
    _seed(fresh_env, "FP-BOOST", wins=7, losses=1)  # win_rate ≈ 0.875 > 0.65
    from packages.learning import mistake_memory as mm
    v = mm.evaluate("FP-BOOST")
    assert v.action == "BOOST"
    assert v.size_factor > 1.0


def test_evaluate_warning_marginal(fresh_env) -> None:
    """Warning: 0.35 ≤ win_rate < 0.50 AND streak < STREAK_AVOID."""
    ps = fresh_env
    state = ps.load()
    base = "2026-06-11T00:{:02d}:00+00:00"
    # 3 loss önce, 2 win sonra (streak=0)
    for i, pnl in enumerate([-50.0, -50.0, -50.0, 80.0, 80.0]):
        state.recent_trades.append(
            ps.Trade(
                id=f"w{i}",
                symbol="BTCUSD",
                side="long",
                entry_price=100.0,
                exit_price=101.0,
                pnl_usd=pnl,
                opened_at=base.format(i),
                closed_at=base.format(i),
                close_reason="TP_HIT" if pnl > 0 else "SL_HIT",
                fingerprint="FP-WARN",
                data_verified=True,
            )
        )
    ps.save(state)
    from packages.learning import mistake_memory as mm
    v = mm.evaluate("FP-WARN")
    assert v.action == "WARNING"
    assert 0.0 < v.size_factor < 1.0


def test_evaluate_avoid_on_streak(fresh_env) -> None:
    # 5 win + 3 loss; loss'lar zaman sırasında en sonda → streak=3
    _seed(fresh_env, "FP-STREAK", wins=5, losses=3)
    from packages.learning import mistake_memory as mm
    v = mm.evaluate("FP-STREAK")
    # Win_rate yüksek ama streak avoid > 3 değil; STREAK_AVOID=3 ⇒ AVOID.
    assert v.action == "AVOID"
    assert v.size_factor == 0.0
    assert v.record is not None
    assert v.record.streak_losses >= 3


# ---------------- decision engine wiring ----------------

def _force_decision_pass(monkeypatch):
    """Risk HOLD, consensus güçlü bullish üretsin diye snap/regime mockla."""
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify
    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    return snap, regime


def _force_strong_bullish(monkeypatch, dec_module):
    """build_consensus'ı güçlü bullish (score=85) döndürecek şekilde patch."""
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


def test_decision_avoid_returns_hold(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision
    from packages.learning import mistake_memory as mm

    snap, regime = _force_decision_pass(monkeypatch)
    _force_strong_bullish(monkeypatch, dec)
    hold_risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    def fake_eval(fp, mems=None):
        return mm.MistakeVerdict(
            action="AVOID",
            reason="forced",
            size_factor=0.0,
            evidence=["test"],
            fingerprint=fp,
            record=None,
        )
    monkeypatch.setattr(dec.mistake_memory, "evaluate", fake_eval)

    d = dec.decide_for_symbol("BTCUSD", snap, regime, hold_risk)
    assert d.action == "hold"
    assert "mistake_memory" in d.reason
    assert d.mistake_verdict.get("action") == "AVOID"
    assert d.size_multiplier == 0.0


def test_decision_kill_switch_beats_boost(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision
    from packages.learning import mistake_memory as mm

    snap, regime = _force_decision_pass(monkeypatch)

    def fake_eval(fp, mems=None):
        return mm.MistakeVerdict(
            action="BOOST",
            reason="forced",
            size_factor=1.5,
            evidence=[],
            fingerprint=fp,
        )
    monkeypatch.setattr(dec.mistake_memory, "evaluate", fake_eval)

    kill = RiskDecision(action="KILL_SWITCH", reason="DQS low", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, kill)
    assert d.action == "blocked"
    assert d.size_multiplier == 0.0
    assert d.confidence == 0.0


def test_decision_risk_reduce_beats_boost(fresh_env, monkeypatch) -> None:
    from packages.decision import engine as dec
    from packages.risk.engine import RiskDecision
    from packages.learning import mistake_memory as mm

    snap, regime = _force_decision_pass(monkeypatch)

    def fake_eval(fp, mems=None):
        return mm.MistakeVerdict(
            action="BOOST",
            reason="forced",
            size_factor=1.5,
            evidence=[],
            fingerprint=fp,
        )
    monkeypatch.setattr(dec.mistake_memory, "evaluate", fake_eval)

    rr = RiskDecision(action="RISK_REDUCE", reason="DD", evidence=[])
    d = dec.decide_for_symbol("BTCUSD", snap, regime, rr)
    assert d.action == "hold"
    assert d.size_multiplier == 0.0


def test_decision_dqs_blocked_with_boost_still_no_trade(fresh_env, monkeypatch) -> None:
    """DQS BLOCKED → KILL_SWITCH (risk engine) → blocked; BOOST etkisiz."""
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

    from packages.decision import engine as dec
    from packages.learning import mistake_memory as mm
    from packages.risk.engine import RiskInput

    def fake_eval(fp, mems=None):
        return mm.MistakeVerdict(
            action="BOOST",
            reason="forced",
            size_factor=1.5,
            evidence=[],
            fingerprint=fp,
        )
    monkeypatch.setattr(dec.mistake_memory, "evaluate", fake_eval)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=100_000,
        peak_equity_usd=100_000,
        daily_pnl_usd=0,
        open_position_count=0,
    )
    _, risk, decisions = dec.decide_all(["BTCUSD"], snap, risk_in)
    assert risk.action == "KILL_SWITCH"
    for d in decisions:
        assert d.action == "blocked"
        assert d.size_multiplier == 0.0


# ---------------- endpoint ----------------

def test_mistakes_endpoint_returns_records_and_verdicts(fresh_env) -> None:
    _seed(fresh_env, "FP-AVOID-E", wins=1, losses=5)
    _seed(fresh_env, "FP-BOOST-E", wins=7, losses=1)

    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/learning/mistakes")
    assert r.status_code == 200
    body = r.json()
    assert body["total_fingerprints"] == 2
    actions = {v["action"] for v in body["verdicts"]}
    assert "AVOID" in actions
    assert "BOOST" in actions
    assert body["flagged_count"] >= 2
    assert "thresholds" in body
    assert body["thresholds"]["min_trades"] == 3
