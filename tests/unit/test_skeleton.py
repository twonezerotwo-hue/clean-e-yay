"""Skeleton smoke testleri — paketler import edilir, /health yanıt verir."""
from __future__ import annotations


def test_packages_importable() -> None:
    import packages.agent
    import packages.consensus
    import packages.data
    import packages.decision
    import packages.learning
    import packages.paper
    import packages.regime
    import packages.risk  # noqa: F401


def test_health_endpoint() -> None:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "2.0.0"
    assert body["uptime_sec"] >= 0
