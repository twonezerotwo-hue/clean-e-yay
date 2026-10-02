from __future__ import annotations

from packages.decision.trace import stable_decision_id


def test_stable_decision_id_is_order_independent():
    assert stable_decision_id({"b": 2, "a": 1}) == stable_decision_id({"a": 1, "b": 2})


def test_stable_decision_id_has_trace_prefix():
    assert stable_decision_id({"symbol": "BTCUSD"}).startswith("dec_")
