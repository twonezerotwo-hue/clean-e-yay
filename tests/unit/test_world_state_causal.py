from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.causal.engine import build_shadow
from packages.data.types import PriceQuote
from packages.learning import news_event_study
from packages.world_state.engine import _decay_factor, build, normalized_surprise


def _snapshot(**kwargs):
    rotation = SimpleNamespace(
        status="OK",
        per_symbol={"DXY": 70.0, "SP500": 65.0, "BTCUSD": 60.0, "ETHUSD": 55.0,
                    "HYG": 45.0, "LQD": 55.0, "XAUUSD": 58.0, "XAGUSD": 52.0,
                    "TLT": 53.0, "BRENT": 57.0},
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
    assert world.global_flow_regime in {"RISK_ON", "RISK_OFF", "NEUTRAL", "LIQUIDITY_EXPANSION", "MIXED", "UNKNOWN"}
    assert "rates" in world.missing_inputs
    assert world.macro_sources["US10Y"]["source_type"] == "UNAVAILABLE"


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


def test_runtime_macro_rates_do_not_read_rotation_fixture_keys():
    snap = _snapshot(prices=[PriceQuote(symbol="US10Y", price=4.2, source="fred", verified=True, status="OK")])
    snap.rotation.per_symbol["US10Y"] = 99.0
    world = build(snap)
    assert world.rates_pressure is None
    assert world.macro_sources["US10Y"]["source_type"] == "DIRECT"


def test_headline_taxonomy_and_valid_until_are_independent_of_legacy_prefix():
    now = datetime.now(UTC)
    headline = SimpleNamespace(id="geo-new", title="Iran threatens to close Strait of Hormuz", title_tr=None,
                               verified=True, ts=now, source="Reuters", region="Middle East")
    world = build(_snapshot(headlines=[headline]))
    assert world.geopolitical_events[0].event_type == "CHOKEPOINT_THREAT"
    expired_impact = SimpleNamespace(headline_id="geo-new", event_type="unknown", confidence=0.9,
                                     surprise_level=0.8, expected_half_life_minutes=120,
                                     valid_until=now.replace(year=now.year - 1))
    expired = build(_snapshot(headlines=[headline], catalyst_impacts=[expired_impact]))
    assert expired.geopolitical_events[0].expired is True
    assert expired.geopolitical_events[0].severity == 0.0


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


def test_causal_ledger_deduplicates_and_study_is_observation_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CAUSAL_EVENT_LEDGER_PATH", str(tmp_path / "causal.jsonl"))
    monkeypatch.setenv("CAUSAL_EVENT_STUDY_PATH", str(tmp_path / "study.json"))
    event = {
        "event_id": "geo-1",
        "event_type": "CHOKEPOINT_THREAT",
        "region": "Middle East",
        "channels": {"shipping_risk": 0.8},
        "asset_predictions": {"BRENT": 0.6},
    }
    assert news_event_study.record_causal_events([event, event]) == 1
    table = news_event_study.causal_event_study(
        forward_returns={("geo-1", "BRENT", "1h"): 0.02},
        horizons=("1h",),
        min_n=2,
    )
    bucket = next(iter(table["buckets"].values()))
    assert bucket["n"] == 1
    assert bucket["verdict"] == "INSUFFICIENT"
    assert table["shadow_only"] is True
    assert table["auto_promotion"] is False


def test_causal_backtest_reports_divergence_without_promotion():
    report = news_event_study.causal_backtest([
        {"asset": "BRENT", "causal_direction": 1, "legacy_direction": -1, "forward_return": 0.02}
    ], min_n=2)
    assert report["divergence_count"] == 1
    assert report["causal_correct_when_legacy_wrong"] == 1
    assert report["shadow_only"] is True


def test_decay_half_life_and_source_diversity_are_applied():
    assert _decay_factor(0.0, 60) == 1.0
    assert _decay_factor(60.0 * 60.0, 60) == 0.5
    now = datetime.now(UTC)
    impact_a = SimpleNamespace(
        headline_id="h1", event_type="geopolitical_escalation", confidence=0.7,
        surprise_level=0.8, expected_half_life_minutes=60, valid_until=None,
    )
    impact_b = SimpleNamespace(
        headline_id="h2", event_type="geopolitical_escalation", confidence=0.7,
        surprise_level=0.8, expected_half_life_minutes=60, valid_until=None,
    )
    h1 = SimpleNamespace(id="h1", title="Missile attack threatens shipping", title_tr=None,
                         verified=True, ts=now, source="Reuters", region="X")
    h2 = SimpleNamespace(id="h2", title="Missile attack threatens shipping", title_tr=None,
                         verified=True, ts=now, source="AP", region="X")
    world = build(_snapshot(headlines=[h1, h2], catalyst_impacts=[impact_a, impact_b]))
    event = world.geopolitical_events[0]
    assert event.source_diversity == 2
    assert event.independent_confirmation_count == 2
    assert event.decay_factor == 1.0


def test_statement_authority_numeric_and_repetition_are_deterministic():
    now = datetime.now(UTC)
    first = SimpleNamespace(id="s1", title="Fed Chair Powell says hawkish higher for longer",
                            title_tr=None, verified=True, source="Federal Reserve official", ts=now,
                            actual=5.5, expected=5.0, historical_surprise_volatility=0.25)
    repeated = SimpleNamespace(id="s2", title="Fed Chair Powell says hawkish higher for longer",
                               title_tr=None, verified=True, source="Federal Reserve official", ts=now)
    world = build(_snapshot(headlines=[first, repeated]))
    assert world.statements[0].speaker_role == "chair"
    assert world.statements[0].authority_score == 1.0
    assert world.statements[0].numeric_surprise == 1.0
    assert world.statements[1].repetition_score == 1.0
    assert world.statements[1].new_information_score < world.statements[0].new_information_score


def test_causal_graph_exposes_actual_edges_and_consensus():
    world = build(_snapshot())
    shadow = build_shadow(world, ["BTCUSD"], legacy_scores={"BTCUSD": {"score": 62.0, "direction": "bullish"}})
    assert shadow.edges
    assert all(edge.source_value is not None and edge.contribution is not None for edge in shadow.edges)
    assert shadow.causal_consensus[0]["legacy_score"] == 62.0
    assert shadow.conflict_shadow[0]["final_action"] == "UNAVAILABLE"
