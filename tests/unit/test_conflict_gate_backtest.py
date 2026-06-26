"""Faz 9A — conflict_gate_backtest.py retrospektif doğrulama testleri.

Read-only: gerçekleşmiş outcome'ları, aynı (snapshot_id, symbol) için yazılmış
shadow gözlem kaydındaki setup_conflict ile eşleştirip route bazında
win-rate/avg_pnl üretir. Karar zincirine bağlı değildir.
"""
from __future__ import annotations

import json

import pytest

from packages.decision import conflict_gate_backtest
from packages.learning.outcomes import CanonicalOutcome


def _outcome(*, trade_id, symbol, timeframe, pnl, snapshot_id) -> CanonicalOutcome:
    return CanonicalOutcome(
        trade_id=trade_id,
        symbol=symbol,
        timeframe=timeframe,
        opened_at="2026-01-01T00:00:00+00:00",
        closed_at="2026-01-01T01:00:00+00:00",
        duration_seconds=3600.0,
        direction="long",
        open_price=100.0,
        close_price=101.0 if pnl > 0 else 99.0,
        pnl=pnl,
        pnl_pct=1.0,
        open_reason="test",
        close_reason="TP_HIT" if pnl > 0 else "SL_HIT",
        fingerprint=None,
        regime="trend",
        dominant_module="sentinel",
        candidate_action="open_long",
        final_action="open_long",
        snapshot_id=snapshot_id,
    )


def _write_shadow_jsonl(path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _shadow_record(snapshot_id, symbol, *, setup_type, conflict_final_action) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "symbols": [
            {
                "symbol": symbol,
                "setup_conflict": {
                    "setup_type": setup_type,
                    "conflict_final_action": conflict_final_action,
                },
            }
        ],
    }


def test_unmatched_when_no_shadow_file(tmp_path):
    outcomes = [_outcome(trade_id="t1", symbol="BTCUSD", timeframe="1d", pnl=10.0, snapshot_id="snap1")]
    report = conflict_gate_backtest.validation_report(
        outcomes=outcomes, shadow_path=tmp_path / "missing.jsonl"
    )
    assert report["_unmatched_no_shadow_data"] == 1


def test_matches_by_snapshot_and_symbol_buckets_by_route(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    _write_shadow_jsonl(
        shadow_path,
        [
            _shadow_record("snap1", "BTCUSD", setup_type="TREND_LONG", conflict_final_action="CANDIDATE_OPEN"),
            _shadow_record("snap2", "BTCUSD", setup_type="TREND_LONG", conflict_final_action="BLOCKED"),
        ],
    )
    outcomes = [
        _outcome(trade_id="t1", symbol="BTCUSD", timeframe="1d", pnl=10.0, snapshot_id="snap1"),
        _outcome(trade_id="t2", symbol="BTCUSD", timeframe="1d", pnl=-5.0, snapshot_id="snap2"),
    ]
    report = conflict_gate_backtest.validation_report(outcomes=outcomes, shadow_path=shadow_path)
    # SWING profile (1d) HARD mode: CANDIDATE_OPEN -> open ; BLOCKED -> block
    assert report["SWING"]["open"] == {"n": 1, "win_rate": 1.0, "avg_pnl": 10.0}
    assert report["SWING"]["block"] == {"n": 1, "win_rate": 0.0, "avg_pnl": -5.0}
    assert report["_unmatched_no_shadow_data"] == 0


def test_soft_mode_reduced_bucket_is_distinct_from_open(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    _write_shadow_jsonl(
        shadow_path,
        [_shadow_record("snap1", "ETHUSD", setup_type="TREND_LONG", conflict_final_action="NO_TRADE")],
    )
    outcomes = [_outcome(trade_id="t1", symbol="ETHUSD", timeframe="1h", pnl=3.0, snapshot_id="snap1")]
    report = conflict_gate_backtest.validation_report(outcomes=outcomes, shadow_path=shadow_path)
    # INTRADAY (1h) SOFT mode: NO_TRADE -> open_reduced
    assert report["INTRADAY"]["open_reduced"] == {"n": 1, "win_rate": 1.0, "avg_pnl": 3.0}


def test_no_trade_setup_type_yields_no_profile_and_is_unmatched(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    _write_shadow_jsonl(
        shadow_path,
        [_shadow_record("snap1", "BTCUSD", setup_type="NO_TRADE", conflict_final_action="NO_TRADE")],
    )
    outcomes = [_outcome(trade_id="t1", symbol="BTCUSD", timeframe="1d", pnl=1.0, snapshot_id="snap1")]
    report = conflict_gate_backtest.validation_report(outcomes=outcomes, shadow_path=shadow_path)
    assert report["_unmatched_no_shadow_data"] == 1


def test_missing_outcome_snapshot_id_is_unmatched(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    _write_shadow_jsonl(shadow_path, [])
    outcomes = [_outcome(trade_id="t1", symbol="BTCUSD", timeframe="1d", pnl=1.0, snapshot_id=None)]
    report = conflict_gate_backtest.validation_report(outcomes=outcomes, shadow_path=shadow_path)
    assert report["_unmatched_no_shadow_data"] == 1


def test_corrupt_shadow_line_is_skipped_not_raised(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    shadow_path.write_text("not json\n" + json.dumps(_shadow_record("snap1", "BTCUSD", setup_type="TREND_LONG", conflict_final_action="CANDIDATE_OPEN")) + "\n", encoding="utf-8")
    outcomes = [_outcome(trade_id="t1", symbol="BTCUSD", timeframe="1d", pnl=2.0, snapshot_id="snap1")]
    report = conflict_gate_backtest.validation_report(outcomes=outcomes, shadow_path=shadow_path)
    assert report["SWING"]["open"]["n"] == 1


def test_custom_profile_modes_override_default():
    report = conflict_gate_backtest.validation_report(
        outcomes=[], shadow_path=None, profile_modes={"SWING": "OFF"}
    )
    assert report["_unmatched_no_shadow_data"] == 0
