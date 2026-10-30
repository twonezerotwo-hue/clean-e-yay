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


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, *a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_monthly_cap_pauses_key_and_retries_keyless(monkeypatch, tmp_path) -> None:
    # Aylık kota dolunca (429/10006) aynı istek anahtarsız genel uçtan tekrarlanır.
    import io
    import urllib.error

    from packages.data.providers import coingecko_auth, quota

    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "quota.json"))
    monkeypatch.setenv("COINGECKO_API_KEY", "demo-key")
    quota.reset_cache()
    seen = []

    def fake_urlopen(req, timeout=None):
        keyed = "X-cg-demo-api-key" in req.headers or "x-cg-demo-api-key" in {k.lower() for k in req.headers}
        seen.append(keyed)
        if keyed:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b'{"status":{"error_code":10006}}'))
        return _Resp(b'{"bitcoin":{"usd":77000}}')

    monkeypatch.setattr(coingecko.urllib.request, "urlopen", fake_urlopen)
    out = coingecko._fetch_many({"BTCUSD": "bitcoin"})
    assert out["BTCUSD"].price == 77000.0
    assert seen == [True, False]
    assert coingecko_auth.key_paused() and "x-cg-demo-api-key" not in coingecko_auth.headers()
    quota.reset_cache()


def test_failed_fetch_backs_off(monkeypatch, tmp_path) -> None:
    # Başarısız toplu istekten sonra 10 dakika ağa çıkılmaz (her tick yeniden deneme yok).
    monkeypatch.setenv("PRICE_CACHE_DIR", str(tmp_path))
    coingecko._CACHE.clear()
    calls = []
    monkeypatch.setattr(coingecko, "_fetch_many", lambda ids: calls.append(ids) or {})
    assert coingecko.get_quote("BTCUSD") is None
    assert coingecko.get_quote("ETHUSD") is None
    assert len(calls) == 1
