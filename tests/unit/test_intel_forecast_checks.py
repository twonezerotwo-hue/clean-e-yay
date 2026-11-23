"""Haber öngörüsü × canlı aday teyit/çelişki kontrolü (brifing ve sohbet kanıtı; karar değişmez)."""
from __future__ import annotations

from packages.discovery.intel import forecast_checks

FORECASTS = {
    "BTCUSD": {"direction": "down", "strength": 55, "evidence": [{"title": "Exchange hack drains reserves"}]},
    "XAUUSD": {"direction": "up", "strength": 30, "evidence": [{"title": "Gold demand rises"}]},
    "BRENT": {"direction": "up", "strength": 10},                          # zayıf → sayılmaz
}
CELLS = [
    {"symbol": "BTCUSD", "timeframe": "1h", "candidate_action": "open_long", "action": "hold", "score": 62},
    {"symbol": "XAUUSD", "timeframe": "1d", "candidate_action": "open_long", "action": "open_long", "score": 66},
    {"symbol": "BRENT", "timeframe": "4h", "candidate_action": "open_long", "action": "hold", "score": 60},
    {"symbol": "DXY", "timeframe": "1h", "candidate_action": "hold", "action": "hold", "score": 50},
]


def test_checks_classify_confirm_and_conflict():
    out = forecast_checks(CELLS, FORECASTS)
    assert [(c["symbol"], c["relation"]) for c in out] == [("BTCUSD", "conflict"), ("XAUUSD", "confirm")]
    assert out[0]["evidence"] == "Exchange hack drains reserves" and out[0]["final_action"] == "hold"
