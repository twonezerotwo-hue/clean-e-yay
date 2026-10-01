from __future__ import annotations

from packages.discovery import build_world_candidates


def test_world_candidates_are_ranked_but_remain_observation_only():
    result = build_world_candidates(
        {"affected_assets": ["BRENT"], "factor_channels": ["energy_supply_risk"]},
        {
            "events": [{
                "scenarios": [{
                    "scenario_id": "CHOKEPOINT_DISRUPTION",
                    "probability": 0.8,
                    "affected_assets": {"BRENT": 0.7},
                    "factor_channels": ["energy_supply_risk"],
                }],
            }],
        },
    )

    assert result["status"] == "OK"
    candidate = result["candidates"][0]
    assert candidate["symbol"] == "BRENT"
    assert candidate["known_asset"] is True
    assert candidate["trade_universe_member"] is True
    assert candidate["promotion_status"] == "OBSERVE_ONLY"
    assert result["promotion_policy"] == "owner_or_discovery_promotion_only"
    assert "candidate_list_does_not_change_trade_universe" in result["warnings"]


def test_unknown_candidate_requires_provider_and_liquidity_before_promotion():
    result = build_world_candidates(
        {},
        {"events": [{"scenarios": [{
            "scenario_id": "REGIONAL_ESCALATION",
            "probability": 0.5,
            "affected_assets": {"UNLISTED_GAS": 0.9},
        }]}]},
    )

    candidate = result["candidates"][0]
    assert candidate["known_asset"] is False
    assert candidate["trade_universe_member"] is False
    assert candidate["missing_inputs"] == ["liquidity", "provider_identity"]
    assert candidate["promotion_status"] == "OBSERVE_ONLY"


def test_malformed_scenario_values_are_fail_soft():
    result = build_world_candidates(
        {},
        {"events": [{"scenarios": [{
            "scenario_id": "bad",
            "probability": "not-a-number",
            "affected_assets": {"BRENT": "also-not-a-number"},
        }]}]},
    )
    assert result["status"] == "NO_MATCH"
    assert result["candidate_count"] == 0
