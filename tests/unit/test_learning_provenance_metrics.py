"""Premium performans yüzeyi ve eksik karar atfı için regresyon testleri."""
from __future__ import annotations

from packages.learning import outcomes
from packages.learning.summary import _performance_snapshot


def _entry(*, diagnostics=None, pnl=10.0):
    row = {
        "trade_id": "t1",
        "symbol": "BTCUSD",
        "side": "long",
        "timeframe": "1h",
        "opening_signal": {
            "fingerprint": "BTCUSD|v2|1h|NEUTRAL|bullish|S55|C|touche",
            "data_verified": True,
        },
        "exit": {"reason": "TP_HIT", "policy": 2},
        "outcome": {"entry_price": 100.0, "exit_price": 101.0, "pnl_usd": pnl},
    }
    if diagnostics is not None:
        row["diagnostics"] = diagnostics
    return row


def test_incomplete_decision_attribution_is_visible_and_not_learned():
    clean = outcomes.build_outcome_from_log_entry(_entry(diagnostics=[]))
    incomplete = outcomes.build_outcome_from_log_entry(
        _entry(diagnostics=["dqs_missing", "risk_action_missing"], pnl=-10.0)
    )

    assert clean.provenance_complete is True
    assert incomplete.provenance_complete is False
    assert incomplete.provenance_missing == ["dqs_missing", "risk_action_missing"]
    assert outcomes.learning_grade([clean, incomplete]) == [clean]


def test_clean_performance_uses_r_and_does_not_count_breakeven_as_loss():
    win = outcomes.build_outcome_from_log_entry(_entry(diagnostics=[], pnl=10.0))
    loss = outcomes.build_outcome_from_log_entry(_entry(diagnostics=[], pnl=-5.0))
    be = outcomes.build_outcome_from_log_entry(_entry(diagnostics=[], pnl=0.0))

    result = _performance_snapshot([win, loss, be])
    assert result["total_trades"] == 3
    assert result["wins"] == 1
    assert result["losses"] == 1
    assert result["breakeven"] == 1
    assert result["win_rate"] == 0.5
    assert result["sample_sufficient"] is False


def test_current_trade_with_config_stamp_requires_open_attribution():
    from packages.paper.state import Trade

    trade = Trade(
        id="current",
        symbol="BTCUSD",
        side="long",
        entry_price=100.0,
        exit_price=99.0,
        pnl_usd=-10.0,
        opened_at="2026-10-22T00:00:00+00:00",
        closed_at="2026-10-22T01:00:00+00:00",
        close_reason="SL_HIT",
        fingerprint="BTCUSD|v2|1h|NEUTRAL|bullish|S55|C|touche",
        data_verified=True,
        open_config_provenance={"weights_version": "1.17.0"},
    )
    result = outcomes.build_outcome(trade)
    assert result.provenance_complete is False
    assert "dqs_missing" in result.provenance_missing
