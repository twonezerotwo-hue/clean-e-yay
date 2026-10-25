from datetime import UTC, datetime

from packages.data.quality.dqs import compute
from packages.data.types import PriceQuote


def quote(verified, price=100.0, status=None):
    return PriceQuote(
        symbol="BTCUSD",
        price=price,
        ts=datetime.now(UTC),
        source="test",
        verified=verified,
        status=status or ("OK" if verified else "MOCK"),
    )


def test_unverified_nonmock_price_is_blocked():
    r = compute([quote(False, status="OK")], ["BTCUSD"])
    assert r.status == "BLOCKED"
    assert r.score == 0.0


def test_mock_fixture_remains_simulation_compatible():
    r = compute([quote(False, status="MOCK")], ["BTCUSD"])
    assert r.status != "BLOCKED"
    assert r.fallback_used is True
    assert r.decision_usage == 0.0


def test_verified_live_price_remains_healthy():
    r = compute([quote(True)], ["BTCUSD"])
    assert r.status == "OK"
    assert r.score >= 99.0


def test_missing_price_is_blocked():
    r = compute(
        [quote(False, None, "DATA_UNAVAILABLE")],
        ["BTCUSD"],
    )
    assert r.status == "BLOCKED"
