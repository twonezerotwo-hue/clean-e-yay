"""Veri hijyeni testleri (owner kararı 2026-07-12).

Fingerprint'i çözülemeyen legacy kayıtlar (regime=UNKNOWN) learning_grade
süzgecinden geçemez; v2 fingerprint'li kayıtlar aynen kalır. Ölçülen gerçek:
13 legacy işlem edge kanıtını şişiriyordu (ort +6.3$ görünen sistem temiz
veride -7.3$) ve UNKNOWN kovalarıyla tabloları kirletiyordu.
"""
from __future__ import annotations

from packages.learning import outcomes as om


def _entry(fingerprint, pnl=10.0):
    return {
        "trade_id": "t1", "symbol": "BTCUSD", "side": "long",
        "timeframe": "4h", "opened_at": None, "closed_at": None,
        "opening_signal": {"fingerprint": fingerprint, "data_verified": True},
        "exit": {}, "outcome": {"entry_price": 100.0, "exit_price": 101.0,
                                "pnl_usd": pnl},
    }


def test_legacy_entry_becomes_unknown_regime():
    o = om.build_outcome_from_log_entry(_entry(None))
    assert o.regime == "UNKNOWN"
    o2 = om.build_outcome_from_log_entry(
        _entry("BTCUSD|v2|4h|NEUTRAL|bullish|S55|C|touche"))
    assert o2.regime == "NEUTRAL"


def test_learning_grade_quarantines_legacy():
    legacy = om.build_outcome_from_log_entry(_entry(None, pnl=2456.0))
    clean = om.build_outcome_from_log_entry(
        _entry("BTCUSD|v2|4h|NEUTRAL|bullish|S55|C|touche"))
    graded = om.learning_grade([legacy, clean])
    assert graded == [clean]


def test_learning_grade_empty_and_all_clean():
    assert om.learning_grade([]) == []
    clean = om.build_outcome_from_log_entry(
        _entry("BTCUSD|v2|1d|OFFENSIVE|bullish|S60|B|fundamental"))
    assert om.learning_grade([clean]) == [clean]
