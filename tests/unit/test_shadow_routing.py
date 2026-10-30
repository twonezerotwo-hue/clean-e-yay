"""Birleşik gölge kanıtı raporu — salt gözlem ve paper-safe sınırları."""
from __future__ import annotations

from packages.learning import shadow_routing


def test_report_is_shadow_only(monkeypatch):
    monkeypatch.setattr(
        shadow_routing,
        "_counterfactual_summary",
        lambda: {
            "snapshots": 2,
            "symbols_with_candidate": 1,
            "candidate_entry_cells": 3,
            "candidate_not_actionable_symbols": 1,
            "blocked_by": {"risk_gate:NO_POSITION_INCREASE": 1},
            "measurement": "candidate_action_vs_final_action",
        },
    )
    monkeypatch.setattr(
        shadow_routing,
        "_asset_evidence",
        lambda: {"status": "NOT_READY", "ready_symbols": [], "candidates": [], "shadow_only": True},
    )
    monkeypatch.setattr(
        shadow_routing,
        "_news_evidence",
        lambda: {"resolved_total": 4, "shadow_only": True},
    )
    report = shadow_routing.build_report()
    assert report["shadow_only"] is True
    assert report["live_decision_changed"] is False
    assert report["paper_safe"] is True
    assert report["no_execution"] is True
    assert report["counterfactual"]["candidate_entry_cells"] == 3
    assert report["routing"]["automatic_activation"] is False


def test_viewmodel_without_artifact_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_ROUTING_PATH", str(tmp_path / "missing.json"))
    view = shadow_routing.viewmodel()
    assert view["status"] == "NO_DATA"
    assert view["shadow_only"] is True
    assert view["no_execution"] is True


def test_disabled_runtime_does_not_expose_stale_artifact(monkeypatch, tmp_path):
    path = tmp_path / "shadow.json"
    path.write_text('{"status":"OK","shadow_only":true,"live_decision_changed":false}', encoding="utf-8")
    monkeypatch.setenv("SHADOW_ROUTING_PATH", str(path))
    view = shadow_routing.viewmodel()
    assert view["status"] == "DISABLED"
    assert view["runtime_enabled"] is False
    assert view["historical_read_only"] is True
    assert view["historical_artifact_available"] is True
