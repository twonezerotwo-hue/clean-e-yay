from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.paper.news_setup import sync
from packages.paper.state import PaperState


def _evidence():
    return {
        "geopolitical_events": [
            {
                "event_id": "evt-1",
                "event_type": "MISSILE_ATTACK",
                "source_confidence": 0.95,
                "evidence": ["verified headline"],
            }
        ]
    }


def _shadow():
    return {
        "causal_consensus": [
            {
                "symbol": "BTCUSD",
                "timeframe": "1d",
                "world_thesis_direction": "bearish",
                "world_score": 35.0,
                "confidence": 0.8,
                "technical_confirmation": -0.3,
                "confluence_state": "STRONG_CONFLUENCE",
            }
        ],
        "forecasts": [
            {
                "symbol": "BTCUSD",
                "horizon": "1d",
                "point_estimate": 84_000,
                "p10": 80_000,
                "p50": 84_000,
                "p90": 88_000,
            }
        ],
    }


def test_news_setup_waits_for_risk_gate_without_opening():
    state = PaperState(100_000, 100_000)
    result = sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[],
        risk_action="NO_POSITION_INCREASE",
        snapshot_id="snap-1",
    )
    assert result["created"] == 1
    assert state.open_positions == []
    setup = state.news_prepared_setups[0]
    assert setup.status == "WAITING_RISK"
    assert setup.last_blocker == "risk_gate:NO_POSITION_INCREASE"


def test_news_setup_marks_canonical_activation_only_after_position_exists():
    state = PaperState(100_000, 100_000)
    now = datetime.now(UTC)
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short")],
        risk_action="HOLD",
        snapshot_id="snap-1",
        now=now,
    )
    assert state.news_prepared_setups[0].status == "ARMED"
    state.open_positions.append(SimpleNamespace(symbol="BTCUSD", timeframe="1d", side="short"))
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_100},
        decisions=[],
        risk_action="HOLD",
        snapshot_id="snap-2",
        now=now + timedelta(minutes=1),
    )
    assert state.news_prepared_setups[0].status == "ACTIVATED"


def test_news_setup_title_is_the_events_own_headline_not_first_snapshot_headline():
    state = PaperState(100_000, 100_000)
    world = _evidence()
    world["geopolitical_events"][0]["evidence"] = ["causal:BTCUSD/1d", "Pentagon raises combat pay amid Iran war"]
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=world,
        prices={"BTCUSD": 85_000},
        decisions=[],
        risk_action="HOLD",
        snapshot_id="snap-1",
    )
    assert state.news_prepared_setups[0].news_title == "Pentagon raises combat pay amid Iran war"


def test_news_setup_title_falls_back_to_event_type_without_headline_evidence():
    state = PaperState(100_000, 100_000)
    world = _evidence()
    world["geopolitical_events"][0]["evidence"] = []
    sync(state, causal_shadow=_shadow(), world_state=world, prices={"BTCUSD": 85_000},
         decisions=[], risk_action="HOLD", snapshot_id="snap-1")
    assert state.news_prepared_setups[0].news_title == "Missile Attack"
