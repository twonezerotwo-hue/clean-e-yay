"""G4-real — provenance helper + 3 router'da `mode` block.

- LIVE: live providers patched success → mode.live_data=True, label=LIVE.
- MOCK_MODE: PRICE_USE_MOCK=true → label=MOCK_MODE, mock_warning=True.
- SIMULATION: test fixture (TEST_USE_MOCK=true) → label=SIMULATION.
- INSUFFICIENT_DATA: live fail → DQS BLOCKED → label=INSUFFICIENT_DATA.
- AIReport simulation altında verdict satırının önüne disclaimer eklenir.
- dashboard_state.module_health.data status mode'a göre.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def runtime(monkeypatch):
    """Live-only runtime simüle et (TEST_USE_MOCK/PRICE_USE_MOCK kapalı)."""
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("PRICE_USE_MOCK", raising=False)
    from packages.data.providers import price
    price.reset_provider_status()
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    return price


def _patch_live_success(monkeypatch, price_mod) -> None:
    from packages.data.types import PriceQuote, utcnow

    def _fake(symbol: str):
        return PriceQuote(
            symbol=symbol,
            price=100.0 + (hash(symbol) % 1000) / 10.0,
            ts=utcnow(),
            source="coingecko" if symbol in price_mod.coingecko.SUPPORTED else
                   "yfinance" if symbol in price_mod.yfinance.SUPPORTED else "fred",
            verified=True,
            status="OK",
        )
    monkeypatch.setattr(price_mod.coingecko, "get_quote", _fake)
    monkeypatch.setattr(price_mod.yfinance, "get_quote", _fake)
    monkeypatch.setattr(price_mod.fred, "get_quote", _fake)


def _patch_live_fail(monkeypatch, price_mod) -> None:
    monkeypatch.setattr(price_mod.coingecko, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.yfinance, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.fred, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.twelvedata, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.alphavantage, "get_quote", lambda s: None)
    monkeypatch.setattr(price_mod.finnhub, "get_quote", lambda s: None)


# ---------- provenance helper ----------

def test_provenance_live_when_all_verified(runtime, monkeypatch) -> None:
    _patch_live_success(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    from packages.data.provenance import data_provenance
    pl._CACHE.clear()
    snap = pl.build_snapshot()
    prov = data_provenance(snap)
    assert prov["label"] == "LIVE"
    assert prov["live_data"] is True
    assert prov["mock_mode"] is False
    assert prov["mock_warning"] is False


def test_provenance_mock_mode_when_runtime_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.setenv("PRICE_USE_MOCK", "true")
    from packages.data.providers import price
    price.reset_provider_status()
    from packages.data.ingestion import pipeline as pl
    from packages.data.provenance import data_provenance
    pl._CACHE.clear()
    snap = pl.build_snapshot()
    prov = data_provenance(snap)
    assert prov["label"] == "MOCK_MODE"
    assert prov["live_data"] is False
    assert prov["mock_warning"] is True


def test_provenance_simulation_under_test_fixture() -> None:
    # conftest TEST_USE_MOCK=true set ediyor.
    from packages.data.ingestion import pipeline as pl
    from packages.data.provenance import data_provenance
    pl._CACHE.clear()
    snap = pl.build_snapshot()
    prov = data_provenance(snap)
    assert prov["label"] == "SIMULATION"
    assert prov["live_data"] is False
    assert prov["test_mock"] is True
    assert prov["mock_warning"] is False


def test_provenance_insufficient_when_live_fail(runtime, monkeypatch) -> None:
    _patch_live_fail(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    from packages.data.provenance import data_provenance
    pl._CACHE.clear()
    snap = pl.build_snapshot()
    prov = data_provenance(snap)
    assert prov["label"] == "INSUFFICIENT_DATA"
    assert prov["live_data"] is False
    assert prov["dqs_status"] == "BLOCKED"


# ---------- routers mode block ----------

def test_dashboard_state_mode_block_test_fixture() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/dashboard/state")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["label"] == "SIMULATION"
    # data module_health TEST fixture altında degraded:
    assert body["module_health"]["data"]["status"] == "degraded"
    # news her zaman demo damgalı:
    assert body["module_health"]["news"]["status"] == "degraded"
    assert "demo" in body["module_health"]["news"]["notes"].lower()


def test_ai_report_disclaimer_in_simulation() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/ai-report/current")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["live_data"] is False
    assert "[SIMULATION]" in body["narrative"]
    # ilk key signal disclaimer:
    assert body["key_signals"] and "[SIMULATION]" in body["key_signals"][0]


def test_ai_report_no_disclaimer_when_live(runtime, monkeypatch) -> None:
    _patch_live_success(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/ai-report/current")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["live_data"] is True
    assert "[SIMULATION]" not in body["narrative"]
    assert "[MOCK_MODE]" not in body["narrative"]


def test_regime_report_mode_block() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/regime-report/current")
    assert r.status_code == 200
    body = r.json()
    assert "mode" in body
    assert body["mode"]["label"] in {"SIMULATION", "LIVE", "MOCK_MODE", "INSUFFICIENT_DATA"}


def test_data_snapshot_mode_block_includes_label() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"]["label"] in {"SIMULATION", "LIVE", "MOCK_MODE", "INSUFFICIENT_DATA"}
    assert "advisory" in body["mode"]


def test_dashboard_data_health_ok_when_live(runtime, monkeypatch) -> None:
    _patch_live_success(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/dashboard/state")
    assert r.status_code == 200
    body = r.json()
    assert body["module_health"]["data"]["status"] == "ok"
    assert body["module_health"]["data"]["notes"] == "live providers"


def test_dashboard_data_health_down_when_blocked(runtime, monkeypatch) -> None:
    _patch_live_fail(monkeypatch, runtime)
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()
    from apps.api.main import app
    client = TestClient(app)
    r = client.get("/api/v1/dashboard/state")
    assert r.status_code == 200
    body = r.json()
    assert body["module_health"]["data"]["status"] == "down"
    assert "BLOCKED" in body["module_health"]["data"]["notes"]
