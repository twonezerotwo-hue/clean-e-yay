"""G1: price provider orchestrator + fallback davranışı + /data/snapshot."""
from __future__ import annotations

import importlib


def _reload_price(monkeypatch, *, use_mock: bool):
    monkeypatch.setenv("PRICE_USE_MOCK", "true" if use_mock else "false")
    from packages.data.providers import price as price_mod
    importlib.reload(price_mod)
    return price_mod


def test_orchestrator_default_uses_mock(monkeypatch) -> None:
    price = _reload_price(monkeypatch, use_mock=True)
    q = price.get_quote("BTCUSD")
    assert q.source == "mock"
    assert q.fallback is False
    assert q.price > 0


def test_orchestrator_live_falls_back_to_mock_on_error(monkeypatch) -> None:
    price = _reload_price(monkeypatch, use_mock=False)

    # Bütün live sağlayıcıları zorla başarısız yap → mock fallback beklenir.
    monkeypatch.setattr(price.coingecko, "get_quote", lambda s: None)
    monkeypatch.setattr(price.yfinance, "get_quote", lambda s: None)
    monkeypatch.setattr(price.fred, "get_quote", lambda s: None)
    price.reset_provider_status()

    q = price.get_quote("BTCUSD")
    assert q.source == "mock"
    assert q.fallback is True

    status = price.get_provider_status()
    assert status["mock"]["fallbacks"] >= 1
    assert status["coingecko"]["status"] == "degraded"


def test_orchestrator_live_success_marks_provider_ok(monkeypatch) -> None:
    price = _reload_price(monkeypatch, use_mock=False)

    from packages.data.types import PriceQuote, utcnow

    def _fake_cg(symbol: str):
        return PriceQuote(symbol=symbol, price=100.0, ts=utcnow(), source="coingecko")

    monkeypatch.setattr(price.coingecko, "get_quote", _fake_cg)
    price.reset_provider_status()

    q = price.get_quote("BTCUSD")
    assert q.source == "coingecko"
    assert q.fallback is False

    status = price.get_provider_status()
    assert status["coingecko"]["status"] == "ok"
    assert status["coingecko"]["last_success_at"] is not None


def test_data_snapshot_endpoint(monkeypatch) -> None:
    # Default mock — network'e dokunmuyoruz.
    monkeypatch.setenv("PRICE_USE_MOCK", "true")
    from packages.data.providers import price as price_mod
    importlib.reload(price_mod)

    # pipeline cache'ini temizle ki yeni provider değişimini görsün
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "meta" in body
    assert body["meta"]["snapshot_id"].startswith("snap::")
    assert isinstance(body["prices"], list) and body["prices"]
    assert "dqs" in body and 0 <= body["dqs"]["score"] <= 100
    assert "provider_status" in body
    assert "mock" in body["provider_status"]
