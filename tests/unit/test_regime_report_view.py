"""S5 (grup 6): rejim raporu görünümü pakette; API ucu yalnız çağırır, alanlar yerinde."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.regime import report


def test_regime_report_endpoint_uses_package_view():
    body = TestClient(app).get("/api/v1/regime-report/current").json()
    assert {"meta", "mode", "regime_label", "layers", "assets", "headlines", "catalysts", "event_risk"} <= set(body)
    assert body["assets"] and all(a["status"] in {"CONFIRMED", "BLOCKING", "PENDING"} for a in body["assets"])


def test_asset_status_rule(monkeypatch):
    monkeypatch.setattr(report.asset_registry, "snapshot_symbols", lambda: ["X"])
    monkeypatch.setattr(report, "data_provenance", lambda snap: {})

    def view(direction, aligned):
        cons = SimpleNamespace(symbol="X", score=60.0, direction=direction, confluence_aligned=aligned,
                               dominant_module="touche")
        snap = SimpleNamespace(snapshot_id="s", generated_at=datetime(2026, 11, 25, tzinfo=UTC), catalysts=[],
                               headlines=[], quality=SimpleNamespace(score=99.0, fallback_used=False))
        return SimpleNamespace(snap=snap, regime=SimpleNamespace(label="NEUTRAL", dropped=(), layers=[]),
                               consensus=lambda s: cons)

    got = [report.current_view(view(d, a))["assets"][0]["status"]
           for d, a in (("bullish", True), ("neutral", True), ("bearish", False))]
    assert got == ["CONFIRMED", "BLOCKING", "PENDING"]
