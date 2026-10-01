from __future__ import annotations

from packages.scenarios import build_report


def test_scenario_distribution_is_normalized_and_prior_is_explicit():
    report = build_report([{
        "event_id": "geo-1",
        "event_type": "CHOKEPOINT_THREAT",
        "severity": 0.8,
        "source_confidence": 0.8,
        "confirmation_count": 2,
        "official_confirmation": True,
        "decay_factor": 1.0,
    }])
    assert report.status == "OK"
    scenarios = report.events[0]["scenarios"]
    assert round(sum(row["probability"] for row in scenarios), 6) == 1.0
    assert all(row["probability_source"] == "EVIDENCE_ADJUSTED" for row in scenarios)
    assert any(row["scenario_id"] == "CHOKEPOINT_DISRUPTION" for row in scenarios)


def test_scenario_engine_does_not_claim_live_probability_without_evidence():
    report = build_report([{"event_id": "geo-2", "event_type": "CHOKEPOINT_DISRUPTION"}])
    scenarios = report.events[0]["scenarios"]
    assert all(row["probability_source"] == "PRIOR_ONLY" for row in scenarios)
    assert all("prior_only_no_runtime_evidence" in row["warnings"] for row in scenarios)


def test_scenario_engine_skips_unsupported_events():
    report = build_report([{"event_id": "x", "event_type": "EARNINGS"}])
    assert report.status == "NO_MATCH"
    assert report.events == ()
    assert "scenario_event_type_unsupported:EARNINGS" in report.warnings

