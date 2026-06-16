"""Step 9 — /api/v1/decision/shadow read endpoint (observe-only).

The schema conformance of this no-param GET is auto-checked by test_openapi_contract.
These cover the behaviour: the Phase-A invariant (affected_paper always false), the
empty-shell shape when no shadow log exists, and that a recorded comparison surfaces.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.decision import shadow

client = TestClient(app)

_REQUIRED = {"available", "affect_decision", "affected_paper", "summary", "calibration", "rows"}
_SUMMARY_KEYS = {
    "agree_entry", "agree_flat", "disagree_direction", "live_only_entry", "shadow_only_entry",
}


def test_shadow_endpoint_is_observe_only_shape():
    r = client.get("/api/v1/decision/shadow")
    assert r.status_code == 200
    body = r.json()
    assert _REQUIRED <= set(body)
    assert body["affected_paper"] is False  # Phase A invariant — read endpoint never moves paper
    assert isinstance(body["rows"], list)
    assert _SUMMARY_KEYS <= set(body["summary"])
    assert {"tf_weights_trusted", "calibrated_timeframes", "per_timeframe"} <= set(body["calibration"])


def test_shadow_endpoint_surfaces_recorded_comparison(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    rec = shadow.build_comparison(
        snapshot_id="snap-api",
        risk_action="HOLD",
        live_decisions=[],
        shadow_views=[],
        cfg=shadow.ShadowConfig(enabled=True, affect_decision=False),
        calibration=shadow.calibration_summary(
            {"tf_weights_trusted": False, "min_trades_per_tf": 20,
             "calibrated_timeframes": [], "per_timeframe": []}
        ),
    )
    shadow.record(rec)
    body = client.get("/api/v1/decision/shadow").json()
    assert body["available"] is True
    assert body["affected_paper"] is False
    assert body["recorded_at"] == rec["recorded_at"]
    assert body["calibration"]["tf_weights_trusted"] is False
