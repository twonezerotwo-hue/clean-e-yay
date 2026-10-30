from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.paper.news_setup import mark_activated, match_confluence, sync
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
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short", decision_id="dec-1")],
        risk_action="HOLD",
        snapshot_id="snap-1",
        now=now,
    )
    assert state.news_prepared_setups[0].status == "ARMED"
    assert state.news_prepared_setups[0].decision_id == "dec-1"
    assert state.news_prepared_setups[0].evidence_id
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


def test_news_confluence_match_requires_armed_same_direction_verified_technical_setup():
    state = PaperState(100_000, 100_000)
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short", decision_id="dec-1")],
        risk_action="HOLD",
        snapshot_id="snap-1",
    )
    match = match_confluence(
        state.news_prepared_setups,
        symbol="BTCUSD", timeframe="1d", side="short", price=85_100,
        data_verified=True,
    )
    assert match is not None
    assert match["confluence_state"] == "STRONG_CONFLUENCE"
    assert match["decision_id"] == "dec-1"
    assert match["evidence_id"] == state.news_prepared_setups[0].evidence_id
    assert match_confluence(
        state.news_prepared_setups,
        symbol="BTCUSD", timeframe="1d", side="short", price=85_100,
        data_verified=False,
    ) is None


def test_news_confluence_rejects_different_decision_identity():
    state = PaperState(100_000, 100_000)
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short", decision_id="dec-1")],
        risk_action="HOLD",
        snapshot_id="snap-1",
    )
    assert match_confluence(
        state.news_prepared_setups,
        symbol="BTCUSD", timeframe="1d", side="short", price=85_100,
        data_verified=True, decision_id="dec-2",
    ) is None


def test_news_setup_can_be_activated_in_same_paper_transaction():
    state = PaperState(100_000, 100_000)
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short", decision_id="dec-1")],
        risk_action="HOLD",
        snapshot_id="snap-1",
    )
    setup = state.news_prepared_setups[0]
    assert mark_activated(state, setup.id)
    assert setup.status == "ACTIVATED"
    assert setup.last_blocker is None
    assert not mark_activated(state, "missing")


# ── Otomatik açılışta haber rolü (owner kararı 2026-10-30: conflict_reduce) ──

def _armed_short_state():
    state = PaperState(100_000, 100_000)
    sync(
        state,
        causal_shadow=_shadow(),
        world_state=_evidence(),
        prices={"BTCUSD": 85_000},
        decisions=[SimpleNamespace(symbol="BTCUSD", timeframe="1d", action="open_short", decision_id="dec-1")],
        risk_action="HOLD",
        snapshot_id="snap-1",
    )
    assert state.news_prepared_setups[0].status == "ARMED" and state.news_prepared_setups[0].side == "short"
    return state


def _mode(monkeypatch, **cfg):
    import packages.paper.news_setup as ns

    monkeypatch.setattr(ns, "load_thresholds", lambda: {"news_prepared_setups": {"enabled": True, **cfg}})
    return ns


def _effect(ns, state, side, **kw):
    return ns.auto_open_news_effect(state.news_prepared_setups, symbol="BTCUSD", timeframe="1d", side=side,
                                    price=85_100, data_verified=True, **kw)


def test_conflict_reduce_shrinks_size_when_news_points_the_other_way(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="conflict_reduce", conflict_size_multiplier=0.5)
    out = _effect(ns, _armed_short_state(), "long")
    assert out["allow"] is True and out["size_multiplier"] == 0.5
    assert out["conflict"]["side"] == "short" and out["reason"].startswith("news_conflict:")
    assert out["match"] is None


def test_conflict_reduce_same_direction_only_tags_evidence_never_enlarges(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="conflict_reduce")
    out = _effect(ns, _armed_short_state(), "short")
    assert out["allow"] is True and out["size_multiplier"] == 1.0
    assert out["match"] is not None and out["conflict"] is None          # yalnız kanıt kimliği


def test_conflict_reduce_without_news_is_neutral(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="conflict_reduce")
    out = ns.auto_open_news_effect([], symbol="ETHUSD", timeframe="4h", side="long",
                                   price=3000, data_verified=True)
    assert out == {"mode": "conflict_reduce", "allow": True, "size_multiplier": 1.0, "match": None,
                   "conflict": None, "reason": None}


def test_conflict_multiplier_zero_blocks(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="conflict_reduce", conflict_size_multiplier=0)
    assert _effect(ns, _armed_short_state(), "long")["allow"] is False


def test_require_mode_blocks_without_same_direction_setup(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="require")
    state = _armed_short_state()
    assert _effect(ns, state, "long")["allow"] is False                    # eski 28 Ekim davranışı
    assert _effect(ns, state, "short")["allow"] is True
    assert ns.require_confluence_for_auto_open() is True


def test_shadow_mode_has_no_effect(monkeypatch):
    ns = _mode(monkeypatch, auto_open_mode="shadow")
    out = _effect(ns, _armed_short_state(), "long")
    assert out["allow"] is True and out["size_multiplier"] == 1.0 and out["conflict"] is None


def test_legacy_require_key_still_maps_to_require_mode(monkeypatch):
    ns = _mode(monkeypatch, require_confluence_for_auto_open=True)
    assert ns.auto_open_mode() == "require"
    ns = _mode(monkeypatch)
    assert ns.auto_open_mode() == "shadow" and ns.require_confluence_for_auto_open() is False
