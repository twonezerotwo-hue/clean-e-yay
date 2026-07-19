"""T2 — API yazma-istekleri kilidi (dış denetim P0-4).

Sözleşme:
- API_AUTH_TOKEN env YOKKEN davranış bayt-aynı (tüm mevcut testler bunu zaten
  token'sız koşarak doğrular; kök conftest delenv ile sızmayı keser);
- token TANIMLIYKEN: POST/PUT/PATCH/DELETE Bearer ister (yanlış/eksik → 401,
  handler'a hiç inmez); GET ve CORS preflight (OPTIONS) açık kalır.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-secret-token"


@pytest.fixture
def client(monkeypatch):
    # Bildirim yazımları kök conftest'in izole NOTIFICATIONS_PATH'ine gider.
    monkeypatch.setenv("API_AUTH_TOKEN", TOKEN)
    from apps.api.main import app

    return TestClient(app)


def test_mutating_without_token_401(client) -> None:
    r = client.post("/api/v1/notifications/ack-all")
    assert r.status_code == 401
    assert r.json() == {"detail": "unauthorized"}


def test_mutating_with_wrong_token_401(client) -> None:
    r = client.post(
        "/api/v1/notifications/ack-all",
        headers={"Authorization": "Bearer yanlis-token"},
    )
    assert r.status_code == 401


def test_mutating_with_token_passes(client) -> None:
    r = client.post(
        "/api/v1/notifications/ack-all",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_stays_open(client) -> None:
    """Salt-okuma yüzeyi token'sız çalışır (ilk aşama kararı — yalnız yazma kilitli)."""
    r = client.get("/api/v1/notifications")
    assert r.status_code == 200


def test_options_preflight_stays_open(client) -> None:
    """CORS preflight kilide takılmaz (tarayıcı token gönderemez)."""
    r = client.options(
        "/api/v1/notifications/ack-all",
        headers={
            "Origin": "http://127.0.0.1:4000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in {200, 204}


def test_env_unset_means_open(monkeypatch) -> None:
    """Token tanımsızken yazma istekleri eskisi gibi serbest (bayt-aynı)."""
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    from apps.api.main import app

    r = TestClient(app).post("/api/v1/notifications/ack-all")
    assert r.status_code == 200
