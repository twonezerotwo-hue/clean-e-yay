from __future__ import annotations

from packages.physical import assess_commodity, build_assessments


def _commodity():
    return {
        "id": "commodity:crude_oil",
        "name": "Crude oil",
        "unit": "mbd",
        "asset_symbols": ["BRENT"],
        "factor_channels": ["energy_supply_risk"],
    }


def test_physical_balance_calculates_effective_shock_only_from_complete_observation():
    report = assess_commodity(
        _commodity(),
        {
            "baseline_supply": 100.0,
            "at_risk_supply": 5.0,
            "alternative_supply": 2.0,
            "inventory_release": 1.0,
            "spare_capacity": 0.5,
            "source": "fixture",
            "as_of": "2026-09-30T00:00:00+00:00",
            "verified": True,
        },
        topology_entities=("chokepoint:bab_el_mandeb",),
    )
    assert report.status == "OK"
    assert report.gross_supply_shock == 5.0
    assert report.effective_supply_shock == 1.5
    assert report.effective_supply_shock_pct == 0.015
    assert report.mitigation_coverage == 0.7
    assert report.affected_assets == ("BRENT",)


def test_physical_balance_does_not_treat_missing_buffers_as_zero():
    report = assess_commodity(_commodity(), {"baseline_supply": 100.0, "at_risk_supply": 5.0, "verified": True})
    assert report.status == "PARTIAL"
    assert report.effective_supply_shock is None
    assert "alternative_supply" in report.missing_inputs
    assert "inventory_release" in report.missing_inputs
    assert "spare_capacity" in report.missing_inputs


def test_world_graph_without_current_event_does_not_create_physical_assessment():
    result = build_assessments({"entity_ids": ["country:yemen"]})
    assert result["status"] == "NO_MATCH"
    assert result["assessments"] == {}

