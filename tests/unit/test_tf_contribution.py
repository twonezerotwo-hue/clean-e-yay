"""Per-TF signal-contribution snapshot (closes the deferred attribution path).

Pure math; no I/O. Each test constructs SymbolAgentView-shaped namespaces so the snapshot
computation is exercised in isolation. The honest invariants: NEUTRAL TFs contribute
zero, shares sum to 1.0 when any TF pushed, and the snapshot is empty (not faked) when
nothing pushed.
"""
from __future__ import annotations

from types import SimpleNamespace

from packages.learning import tf_contribution


def _per_tf(d_scores: dict[str, float | None]) -> SimpleNamespace:
    """Build a view stub with the given per-TF direction scores (m15/h1/h4/d1/w1)."""
    per = {
        k: SimpleNamespace(score_overview=SimpleNamespace(direction_score=v))
        for k, v in d_scores.items()
    }
    return SimpleNamespace(agent=SimpleNamespace(per_timeframe=per))


def test_shares_sum_to_one_when_any_tf_pushes():
    view = _per_tf({"m15": None, "h1": 70.0, "h4": 80.0, "d1": 60.0, "w1": None})
    s = tf_contribution.compute_snapshot(view)
    assert abs(sum(s.values()) - 1.0) < 1e-6
    # all entries positive; missing/NEUTRAL omitted
    assert all(v > 0 for v in s.values())
    assert set(s) == {"h1", "h4", "d1"}


def test_empty_snapshot_when_all_neutral_or_missing():
    view = _per_tf({"m15": 50.0, "h1": 50.0, "h4": None, "d1": None, "w1": None})
    assert tf_contribution.compute_snapshot(view) == {}


def test_stronger_push_gets_bigger_share():
    view = _per_tf({"m15": None, "h1": 60.0, "h4": 80.0, "d1": None, "w1": None})
    s = tf_contribution.compute_snapshot(view)
    assert s["h4"] > s["h1"]  # 30 vs 10 raw magnitude


def test_tf_weights_scale_the_share():
    view = _per_tf({"h1": 70.0, "h4": 70.0})
    weights = {"1h": 0.3, "4h": 0.7}  # canonical-keyed
    s = tf_contribution.compute_snapshot(view, tf_weights=weights)
    assert s["h4"] > s["h1"]
    assert abs(s["h1"] + s["h4"] - 1.0) < 1e-6


def test_zero_weight_drops_the_tf():
    view = _per_tf({"h1": 70.0, "h4": 70.0})
    s = tf_contribution.compute_snapshot(view, tf_weights={"1h": 0.0, "4h": 1.0})
    assert s == {"h4": 1.0}


# ── attributed PnL aggregation across closed trades + contribution snapshots ──

def test_attributed_pnl_aggregates_by_strategy_and_tf():
    closed = [
        {"snapshot_id": "s1", "symbol": "BTCUSD", "pnl": 100.0, "strategy": "intraday"},
        {"snapshot_id": "s2", "symbol": "ETHUSD", "pnl": -50.0, "strategy": "intraday"},
    ]
    snaps = [
        {"snapshot_id": "s1", "contributions": {"BTCUSD": {"h1": 0.4, "h4": 0.6}}},
        {"snapshot_id": "s2", "contributions": {"ETHUSD": {"h1": 0.5, "h4": 0.5}}},
    ]
    a = tf_contribution.attributed_pnl_per_tf(closed, snaps)
    assert "intraday" in a
    # BTC: +100 split (40 to h1, 60 to h4). ETH: -50 split (-25, -25).
    assert abs(a["intraday"]["1h"] - (40.0 - 25.0)) < 1e-6
    assert abs(a["intraday"]["4h"] - (60.0 - 25.0)) < 1e-6


def test_attributed_pnl_empty_when_no_matching_snapshot():
    closed = [{"snapshot_id": "x", "symbol": "BTCUSD", "pnl": 100.0, "strategy": "intraday"}]
    snaps = [{"snapshot_id": "y", "contributions": {"BTCUSD": {"h1": 1.0}}}]
    assert tf_contribution.attributed_pnl_per_tf(closed, snaps) == {}
