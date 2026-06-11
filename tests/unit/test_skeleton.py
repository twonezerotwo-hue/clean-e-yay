"""Skeleton smoke test — paketlerin import edilebildiğini doğrular."""
from __future__ import annotations


def test_packages_importable() -> None:
    import packages.agent  # noqa: F401
    import packages.consensus  # noqa: F401
    import packages.data  # noqa: F401
    import packages.decision  # noqa: F401
    import packages.learning  # noqa: F401
    import packages.paper  # noqa: F401
    import packages.regime  # noqa: F401
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
