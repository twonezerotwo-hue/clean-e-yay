from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.causal.engine import build_shadow
from packages.world_state.engine import build, normalized_surprise


def _snapshot(**kwargs):
    rotation = SimpleNamespace(
        status="OK",
        per_symbol={"DXY": 70.0, "SP500": 65.0, "BTCUSD": 60.0, "ETHUSD": 55.0,
                    "HYG": 45.0, "LQD": 55.0, "XAUUSD": 58.0},
        evidence=["rotation fixture"],
    )
    quality = SimpleNamespace(status="OK", score=90.0)
    values = {
        "generated_at": datetime.now(UTC), "rotation": rotation, "quality": quality,
        "headlines": [], "catalysts": [], "catalyst_impacts": [],
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_world_state_reuses_flow_and_keeps_scale_bounded():
    world = build(_snapshot())
    assert -1.0 <= world.usd_pressure <= 1.0
    assert -1.0 <= world.liquidity <= 1.0
    assert world.global_flow_regime in {"RISK_ON", "RISK_OFF", "NEUTRAL", "LIQUIDITY_EXPANSION", "UNKNOWN"}
    assert world.missing_inputs == ()


def test_missing_inputs_are_not_filled_with_fake_neutral():
    snap = _snapshot()
    snap.rotation.per_symbol = {}
    world = build(snap)
    assert world.usd_pressure is None
    assert "DXY" in world.missing_inputs
    assert world.coverage == 0.0


def test_numeric_surprise_requires_all_inputs():
    assert normalized_surprise(110.0, 100.0, 5.0) == 1.0
    assert normalized_surprise(110.0, None, 5.0) is None
    assert normalized_surprise(110.0, 100.0, 0.0) is None


def test_duplicate_headlines_do_not_create_duplicate_geopolitical_events():
    now = datetime.now(UTC)
    impact = SimpleNamespace(
        headline_id="h1", event_type="geopolitical_escalation", confidence=0.8,
        surprise_level=0.7, expected_half_life_minutes=120, valid_until=None,
    )
    duplicate = SimpleNamespace(
        id="h2", title="Missile attack threatens shipping", title_tr=None,
        verified=True, ts=now, source="copy-b", region="X",
    )
    original = SimpleNamespace(
        id="h1", title="Missile attack threatens shipping", title_tr=None,
        verified=True, ts=now, source="source-a", region="X",
    )
    world = build(_snapshot(headlines=[original, duplicate], catalyst_impacts=[impact]))
    assert len(world.geopolitical_events) == 1


def test_causal_shadow_is_evidence_only_and_bounded():
    world = build(_snapshot())
    shadow = build_shadow(world, ["XAUUSD", "BTCUSD", "SP500"], decision_apply=False)
    assert shadow.enabled is True
    assert shadow.decision_apply is False
    assert len(shadow.edges) > 0
    assert {item.symbol for item in shadow.impacts} == {"XAUUSD", "BTCUSD", "SP500"}
    assert all(item.direction_score is None or -1.0 <= item.direction_score <= 1.0 for item in shadow.impacts)


def test_causal_shadow_can_be_disabled_without_side_effects():
    world = build(_snapshot())
    shadow = build_shadow(world, ["BTCUSD"], enabled=False, decision_apply=True)
    assert shadow.enabled is False
    assert shadow.decision_apply is False
    assert shadow.impacts == ()


def test_technical_timing_is_observational_and_separate_from_thesis():
    world = build(_snapshot())
    technicals = {
        "XAUUSD": {
            "4h": SimpleNamespace(direction_score=70.0),
            "1d": SimpleNamespace(direction_score=65.0),
        }
    }
    shadow = build_shadow(world, ["XAUUSD"], technicals=technicals)
    impact = shadow.impacts[0]
    assert impact.direction_score is not None
    assert impact.technical_confirmation == 0.35
    assert impact.timing_status == "CONFIRMED"
    assert shadow.decision_apply is False
