from __future__ import annotations

from packages.learning.performance_readiness import evaluate


def _summary(**overrides):
    performance = {
        "total_trades": 100,
        "expectancy_r": 0.12,
        "sharpe": 0.8,
        "excluded_from_learning": 0,
        "by_timeframe": {"1h": {"trades": 50, "avg_r": 0.08}},
        "cost_r": 0.1,
        "net_expectancy_r": 0.02,
        "max_drawdown_r": -6.0,
        "benchmark": {"system_net_return_pct": 4.0, "benchmark_return_pct": 1.5},
    }
    summary = {
        "verified_outcomes": 100,
        "outcomes_total": 100,
        "walk_forward": {"test_window": 40, "test_win_rate": 0.58, "test_sharpe": 0.4},
        "by_close_reason": {"SL_HIT": {"trades": 10, "avg_r": -0.8}},
    }
    performance.update(overrides.pop("performance", {}))
    summary.update(overrides)
    return performance, summary


def test_readiness_requires_positive_out_of_sample_evidence() -> None:
    performance, summary = _summary()
    report = evaluate(performance, summary)
    assert report["score"] == 100.0
    assert report["status"] == "READY_FOR_OWNER_REVIEW"
    assert report["blockers"] == []
    assert report["automatic_activation"] is False


def test_readiness_surfaces_negative_edge_without_changing_it() -> None:
    performance, summary = _summary(
        performance={
            "expectancy_r": -0.04,
            "sharpe": -0.8,
            "excluded_from_learning": 50,
            "by_timeframe": {"1h": {"trades": 50, "avg_r": -0.08}},
            "net_expectancy_r": -0.14,
            "max_drawdown_r": -22.0,
            "benchmark": {"system_net_return_pct": -3.0, "benchmark_return_pct": 2.0},
        },
        walk_forward={"test_window": 40, "test_win_rate": 0.33, "test_sharpe": -1.2},
        by_close_reason={"SL_HIT": {"trades": 40, "avg_r": -1.45}},
    )
    report = evaluate(performance, summary)
    assert report["status"] == "WAITING_EVIDENCE"
    assert report["score"] < 90
    assert {
        "positive_expectancy",
        "net_of_costs",
        "drawdown",
        "beats_buy_and_hold",
        "positive_sharpe",
        "walk_forward",
        "timeframe_stability",
        "exit_quality",
        "provenance_quality",
    }.issubset(report["blockers"])
    assert report["shadow_only"] is True
    assert report["no_execution"] is True
