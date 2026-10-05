"""Haber → karar GÖLGE girdisi (owner kararı 2026-10-05, üçüncü tur) — ağsız, karar değişmez."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.discovery import news_decision_shadow as nds

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
CFG = {"news_decision_shadow": {"min_strength": 20, "horizons_hours": [4, 24], "dedupe_hours": 4}}
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


def _doc(prices):
    return {"snapshot_id": "snap-1", "decision_matrix": {"cells": CELLS},
            "data_snapshot": {"prices": [{"symbol": s, "price": p} for s, p in prices.items()]}}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DECISION_SHADOW_PATH", str(tmp_path / "nds.jsonl"))
    return tmp_path


def test_checks_classify_confirm_and_conflict():
    out = nds.checks(CELLS, FORECASTS, 20)
    assert [(c["symbol"], c["relation"]) for c in out] == [("BTCUSD", "conflict"), ("XAUUSD", "confirm")]
    assert out[0]["evidence"] == "Exchange hack drains reserves" and out[0]["final_action"] == "hold"


def test_run_records_dedupes_and_resolves(ledger):
    first = nds.run(NOW, forecasts=FORECASTS, snapshot_doc=_doc({"BTCUSD": 100.0, "XAUUSD": 2000.0}),
                    discovery_cfg=CFG)
    assert first == {"status": "OK", "created": 2, "resolved": 0, "rows": 2}
    again = nds.run(NOW + timedelta(hours=1), forecasts=FORECASTS,
                    snapshot_doc=_doc({"BTCUSD": 99.0, "XAUUSD": 2001.0}), discovery_cfg=CFG)
    assert again["created"] == 0                                            # 4 saatlik tekrar engeli
    later = nds.run(NOW + timedelta(hours=5), forecasts={}, discovery_cfg=CFG,
                    snapshot_doc=_doc({"BTCUSD": 97.0, "XAUUSD": 2030.0}))
    assert later["resolved"] == 2                                           # yalnız 4 saatlik ufuk
    sc = nds.scorecard(CFG)
    assert sc["affect_decision"] is False
    assert sc["by_relation"]["conflict"]["4h"] == {"n": 1, "hit": 0, "miss": 1, "flat": 0, "hit_rate": 0.0}
    assert sc["by_relation"]["confirm"]["4h"]["hit_rate"] == 1.0           # haber teyitli aday tuttu
    nds.run(NOW + timedelta(hours=25), forecasts={}, discovery_cfg=CFG,
            snapshot_doc=_doc({"BTCUSD": 100.05, "XAUUSD": 2050.0}))
    day = nds.compact(CFG)["day"]
    assert day["conflict"] == {"n": 1, "hit_rate": None}                    # %0.05 → yatay
    assert day["confirm"]["hit_rate"] == 1.0


def test_affect_decision_is_always_false_even_if_config_says_true():
    cfg = nds.config({"news_decision_shadow": {"affect_decision": True}})
    assert cfg["affect_decision"] is False
