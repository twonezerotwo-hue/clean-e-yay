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


def _mixed_quotes(verified_count: int):
    symbols = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "BRENT"]
    quotes = [
        PriceQuote(
            symbol=symbol,
            price=100.0,
            ts=datetime.now(UTC),
            source="yfinance",
            verified=(i < verified_count),
            status="OK",
        )
        for i, symbol in enumerate(symbols)
    ]
    return compute(quotes, symbols)


def test_mixed_one_of_five_verified_blocks():
    result = _mixed_quotes(1)
    assert result.completeness == 20.0
    assert result.decision_usage == 20.0
    assert result.score <= 20.0
    assert result.score < 55.0
    assert result.status == "BLOCKED"


def test_mixed_four_of_five_verified_never_ok():
    result = _mixed_quotes(4)
    assert result.completeness == 80.0
    assert result.score <= 69.9
    assert result.status == "DEGRADED"


def test_all_five_verified_stays_ok():
    result = _mixed_quotes(5)
    assert result.completeness == 100.0
    assert result.score >= 99.0
    assert result.status == "OK"


def test_none_verified_stays_blocked():
    result = _mixed_quotes(0)
    assert result.score == 0.0
    assert result.status == "BLOCKED"


def test_verified_flag_without_ok_status_not_trusted():
    quotes = [
        PriceQuote(
            symbol="BTCUSD",
            price=100.0,
            ts=datetime.now(UTC),
            source="yfinance",
            verified=True,
            status="DATA_UNAVAILABLE",
        ),
        PriceQuote(
            symbol="ETHUSD",
            price=100.0,
            ts=datetime.now(UTC),
            source="yfinance",
            verified=True,
            status="OK",
        ),
    ]
    result = compute(quotes, ["BTCUSD", "ETHUSD"])
    assert result.completeness == 50.0
    assert result.score <= 50.0
    assert result.status != "OK"


def test_missing_optional_custom_asset_does_not_cap_core_dqs():
    quotes = [
        PriceQuote(
            symbol="BTCUSD",
            price=100.0,
            ts=datetime.now(UTC),
            source="coingecko",
            verified=True,
            status="OK",
        ),
        PriceQuote(
            symbol="SKYAI",
            price=None,
            ts=datetime.now(UTC),
            source="coingecko",
            verified=False,
            status="DATA_UNAVAILABLE",
        ),
    ]
    result = compute(quotes, ["BTCUSD", "SKYAI"], optional_symbols={"SKYAI"})
    assert result.status == "OK"
    assert result.score >= 99.0
    assert result.completeness == 100.0
    assert any("opsiyonel" in note and "SKYAI" in note for note in result.notes)
