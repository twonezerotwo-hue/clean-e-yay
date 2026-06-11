"""G1.1 — runtime mock-yasağı politikası testleri.

- Runtime'da live başarısız → DATA_UNAVAILABLE (mock dönmez).
- FRED_API_KEY yoksa → quote None / DATA_UNAVAILABLE.
- Test fixture (TEST_USE_MOCK=true) hâlâ mock quote döner ama
  verified=False, status="MOCK".
- /data/snapshot crash etmez, sahte fiyat üretmez.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def runtime(monkeypatch):
    """Test mock fixture'ını kapat; live-only runtime simüle et."""
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("PRICE_USE_MOCK", raising=False)
    from packages.data.providers import price
    price.reset_provider_status()
    return price


def _kill_live_providers(monkeypatch, price_mod) -> None:
    monkeypatch.setattr(price_mod.coingecko, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.yfinance, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.fred, "get_quote", lambda s: None)


def test_test_mode_returns_mock_with_mock_status() -> None:
    from packages.data.providers import price
    q = price.get_quote("BTCUSD")
    assert q.source == "mock"
    assert q.status == "MOCK"
    assert q.verified is False
    assert q.price is not None and q.price > 0


def test_runtime_live_failure_returns_data_unavailable(runtime, monkeypatch) -> None:
    _kill_live_providers(monkeypatch, runtime)
    q = runtime.get_quote("BTCUSD")
    assert q.price is None
    assert q.verified is False
    assert q.status == "DATA_UNAVAILABLE"
    assert q.source == "coingecko"
    assert q.error

    status = runtime.get_provider_status()
    assert status["coingecko"]["status"] == "degraded"
    # Mock dağıtılmadı.
    assert status["mock"]["calls"] == 0


def test_runtime_unmapped_symbol_returns_data_unavailable(runtime) -> None:
    q = runtime.get_quote("UNKNOWN_X")
    assert q.price is None
    assert q.status == "DATA_UNAVAILABLE"
    assert q.verified is False
    assert q.error


def test_fred_missing_api_key_yields_none(monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    from packages.data.providers.price import fred
    assert fred.get_quote("US10Y") is None


def test_fred_via_orchestrator_explains_missing_key(runtime, monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    q = runtime.get_quote("US10Y")
    assert q.price is None
    assert q.status == "DATA_UNAVAILABLE"
    assert q.error and "FRED_API_KEY" in q.error


def test_dqs_blocked_when_all_prices_none(runtime, monkeypatch) -> None:
    _kill_live_providers(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    snap = pl.build_snapshot(["BTCUSD", "ETHUSD", "XAUUSD"])
    assert snap.quality.status == "BLOCKED"
    assert snap.quality.score < 40
    assert all(p.price is None for p in snap.prices)


def test_data_snapshot_endpoint_runtime_blocked(runtime, monkeypatch) -> None:
    _kill_live_providers(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["dqs"]["status"] == "BLOCKED"
    assert all(p["price"] is None for p in body["prices"])
    assert body["mode"]["mock_mode"] is False
    assert body["mode"]["mock_warning"] is False


def test_paper_tick_no_open_when_data_unavailable(
    runtime, monkeypatch, tmp_path
) -> None:
    _kill_live_providers(monkeypatch, runtime)
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "blocked.json"))
    import importlib
    from packages.paper import state as st
    importlib.reload(st)

    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    r = client.post("/api/v1/paper-trading/tick")
    assert r.status_code == 200
    body = r.json()
    opens = [a for a in body["actions"] if a["action"] == "open"]
    assert opens == []  # mock fiyatla pozisyon açılmadı


def test_data_snapshot_endpoint_test_mode() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["mock_mode"] is True
    assert body["mode"]["test_mock"] is True
    assert body["mode"]["mock_warning"] is False
    assert any(p["status"] == "MOCK" for p in body["prices"])


def test_runtime_explicit_mock_sets_banner(monkeypatch) -> None:
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.setenv("PRICE_USE_MOCK", "true")
    from packages.data.providers import price
    price.reset_provider_status()

    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["mock_mode"] is True
    assert body["mode"]["mock_warning"] is True
    assert any("MOCK MODE" in w for w in body["warnings"])
