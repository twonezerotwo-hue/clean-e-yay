"""CoinGecko quote cache is shared safely between local worker processes."""

from datetime import UTC, datetime

from packages.data.providers.price import coingecko
from packages.data.types import PriceQuote


def test_quote_uses_ttl_disk_cache_when_process_memory_is_empty(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PRICE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("COINGECKO_PRICE_TTL_SEC", "900")
    coingecko._CACHE.clear()
    quote = PriceQuote(
        symbol="BTCUSD",
        price=100.0,
        ts=datetime.now(UTC),
        source="coingecko",
        verified=True,
        status="OK",
    )
    monkeypatch.setattr(coingecko, "_fetch", lambda symbol, cg_id: quote)
    assert coingecko.get_quote("BTCUSD") == quote

    coingecko._CACHE.clear()

    def fail_fetch(symbol: str, cg_id: str):
        raise AssertionError("network")

    monkeypatch.setattr(coingecko, "_fetch", fail_fetch)
    assert coingecko.get_quote("BTCUSD") == quote
