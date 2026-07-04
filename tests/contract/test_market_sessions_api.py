"""Market-session API — read-only, paper-safe contract.

The /market-sessions/current GET is auto-validated against its schema by
test_openapi_contract.py (no path param). These cover the path-param asset
endpoint, the paper-safety flags, and that the router never mutates paper state.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.paper import state as paper_state

client = TestClient(app)


def test_current_returns_markets_and_paper_safe_flags():
    r = client.get("/api/v1/market-sessions/current")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["markets"], list) and body["markets"]
    assert body["paper_safe"] is True
    assert body["no_execution"] is True
    sample = body["markets"][0]
    for field in ("market_id", "is_open", "session_phase", "holiday_verified", "diagnostics"):
        assert field in sample


def test_asset_endpoint_returns_context_and_decision():
    r = client.get("/api/v1/market-sessions/asset/SPY")
    assert r.status_code == 200
    body = r.json()
    assert body["asset_code"] == "SPY"
    assert body["paper_safe"] is True
    assert body["no_execution"] is True
    ctx = body["asset_context"]
    assert ctx["asset_code"] == "SPY"
    assert "US_EQUITY" in {m["market_id"] for m in ctx["relevant_markets"]}
    decision = body["decision"]
    assert decision["action"] in ("allow", "caution", "manual_ready", "block")
    # Market sessions may only restrict — never boost size.
    assert decision["size_multiplier"] <= 1.0


def test_asset_crypto_allows_24_7():
    body = client.get("/api/v1/market-sessions/asset/BTCUSD").json()
    assert body["decision"]["action"] == "allow"
    assert body["decision"]["size_multiplier"] == 1.0


def test_unknown_asset_is_manual_ready_not_fake_allow():
    # 2026-07-04: caution → manual_ready (takvimi bilinmeyen varlık otomatik açılmaz).
    body = client.get("/api/v1/market-sessions/asset/ZZZZ").json()
    assert body["decision"]["action"] == "manual_ready"
    assert "asset_unmapped" in body["asset_context"]["diagnostics"]


def test_router_does_not_mutate_paper_state():
    before = paper_state.load()
    snapshot = (
        len(before.open_positions),
        len(before.recent_trades),
        len(before.manual_ready),
        before.equity_usd,
    )
    client.get("/api/v1/market-sessions/current")
    client.get("/api/v1/market-sessions/asset/SPY")
    client.get("/api/v1/market-sessions/asset/BTCUSD")
    after = paper_state.load()
    assert (
        len(after.open_positions),
        len(after.recent_trades),
        len(after.manual_ready),
        after.equity_usd,
    ) == snapshot
