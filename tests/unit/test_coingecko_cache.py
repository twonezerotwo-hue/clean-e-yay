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
    monkeypatch.setattr(coingecko, "_fetch_many", lambda ids: {"BTCUSD": quote})
    assert coingecko.get_quote("BTCUSD") == quote

    coingecko._CACHE.clear()

    def fail_fetch(ids):
        raise AssertionError("network")

    monkeypatch.setattr(coingecko, "_fetch_many", fail_fetch)
    assert coingecko.get_quote("BTCUSD") == quote


def test_stale_symbols_refresh_in_one_request(monkeypatch, tmp_path) -> None:
    # Önbellek bayatlayınca bütün CoinGecko sembolleri tek istekte yenilenir.
    monkeypatch.setenv("PRICE_CACHE_DIR", str(tmp_path))
    coingecko._CACHE.clear()
    calls = []

    def fake_many(ids):
        calls.append(dict(ids))
        return {
            sym: PriceQuote(symbol=sym, price=1.0, ts=datetime.now(UTC), source="coingecko", verified=True, status="OK")
            for sym in ids
        }

    monkeypatch.setattr(coingecko, "_fetch_many", fake_many)
    assert coingecko.get_quote("BTCUSD") is not None
    assert coingecko.get_quote("ETHUSD") is not None  # ilk istekte geldi, ağa çıkmaz
    assert len(calls) == 1 and {"BTCUSD", "ETHUSD"} <= set(calls[0])


def test_quota_exhausted_skips_network(monkeypatch, tmp_path) -> None:
    from packages.data.providers import quota

    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "quota.json"))
    monkeypatch.setenv("PROVIDER_QUOTA_COINGECKO_PER_DAY", "0")
    monkeypatch.setenv("PROVIDER_QUOTA_COINGECKO_PER_MINUTE", "1")
    quota.reset_cache()
    assert quota.consume("coingecko") is True
    monkeypatch.setattr(coingecko.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ağ")))
    assert coingecko._fetch_many({"BTCUSD": "bitcoin"}) == {}
    quota.reset_cache()
