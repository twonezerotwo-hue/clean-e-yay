"""H7 — temizlik öncesi çıkış hatası kayıpları (execution_anomaly) öğrenmeden ayrılır."""
from __future__ import annotations

from dataclasses import replace

import pytest

from packages.decision import engine
from packages.learning import cohorts, decision_log, outcomes
from packages.paper import lifecycle
from packages.paper.state import PaperState

pytestmark = pytest.mark.usefixtures("seed_ohlcv_reference")  # BTCUSD@60000


def _closed_trade(reason="SL_HIT", exit_price=58_000.0):
    state = PaperState(equity_usd=100_000.0, peak_equity_usd=100_000.0)
    pos, decision = lifecycle.attempt_open(
        state, symbol="BTCUSD", side="long", entry_price=60_000.0, size_multiplier=0.35,
        timeframe="1d", open_reason="test", snapshot_id="snap::t",
        fingerprint="BTCUSD|v2|1d|NEUTRAL|bullish|S55|X|touche", data_verified=True,
        open_dqs=88.0, open_risk_action="HOLD", open_blocked_by=[],
    )
    assert pos is not None, decision
    return lifecycle.close_position(state, pos, exit_price=exit_price, reason=reason)


def _outcome(**kw):
    trade = _closed_trade()
    o = outcomes.build_outcome(trade)
    return replace(o, **kw)


def test_close_stamps_exit_policy_through_log_and_outcomes():
    trade = _closed_trade()
    assert trade.exit_policy == lifecycle.EXIT_POLICY_VERSION == 2
    entry = decision_log.entry_for(trade)
    assert entry["exit"]["policy"] == 2
    assert outcomes.build_outcome(trade).exit_policy == 2
    assert outcomes.build_outcome_from_log_entry(entry).exit_policy == 2
    legacy = dict(entry, exit={"reason": "SL_HIT"})
    assert outcomes.build_outcome_from_log_entry(legacy).exit_policy == 0


@pytest.mark.parametrize(
    ("policy", "reason", "r", "expected"),
    [
        (0, "SL_HIT", -2.04, True),     # H1: önceki bar kapanışıyla -2R
        (0, "SL_HIT", -8.04, True),     # H2: acil fren yok
        (0, "SL_HIT", -1.40, False),    # normal sınır içi kayıp
        (0, "TP_HIT", -2.00, False),
        (0, "SL_HIT", None, False),     # R bilinmiyor → uydurma yok
        (2, "SL_HIT", -5.00, False),    # düzeltilmiş mantık: gerçek piyasa riski
    ],
)
def test_is_execution_anomaly(policy, reason, r, expected):
    o = _outcome(exit_policy=policy, close_reason=reason, r_multiple=r)
    assert outcomes.is_execution_anomaly(o) is expected


def test_anomalies_leave_learning_and_get_their_own_cohort():
    bad = _outcome(exit_policy=0, close_reason="SL_HIT", r_multiple=-4.3, regime="NEUTRAL")
    ok = _outcome(exit_policy=0, close_reason="SL_HIT", r_multiple=-1.0, regime="NEUTRAL")
    assert outcomes.learning_grade([bad, ok]) == [ok]
    assert outcomes.learning_grade([bad, ok], include_exploration=True) == [ok]
    assert cohorts.classify(bad) == cohorts.EXECUTION_ANOMALY
    summary = cohorts.cohort_summary([bad, ok])
    assert summary[cohorts.EXECUTION_ANOMALY]["trades"] == 1
    assert summary[cohorts.AUTO]["trades"] == 1


def test_recent_edge_brake_ignores_anomalies(monkeypatch):
    normal = [_outcome(exit_policy=2, close_reason="TP_HIT", r_multiple=1.0) for _ in range(10)]
    bad = [_outcome(exit_policy=0, close_reason="SL_HIT", r_multiple=-8.0)]
    monkeypatch.setattr(outcomes, "outcomes_from_state", lambda *a, **k: normal + bad)
    assert engine._recent_edge(lookback=11) == pytest.approx(1.0)
