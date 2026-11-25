"""S1 (grup 6): anlık fiyatlar paralel çekilir ama sonuç ve sıra aynıdır; snapshot parça süreleri kaydedilir."""
from __future__ import annotations

import threading
import time

from packages.data.providers import price
from packages.data.types import PriceQuote


def test_parallel_quotes_match_sequential_and_keep_coingecko_in_one_task(monkeypatch):
    monkeypatch.setenv("TEST_USE_MOCK", "false")
    cg = {"BTCUSD", "ETHUSD"}
    seen_threads: dict[str, int] = {}

    def fake_quote(symbol):
        time.sleep(0.05)
        seen_threads[symbol] = threading.get_ident()
        return PriceQuote(symbol=symbol, price=float(len(symbol)), source="t", verified=True, status="OK")

    monkeypatch.setattr(price, "get_quote", fake_quote)
    monkeypatch.setattr(price, "_primary_for", lambda s: price.coingecko if s in cg else price.yfinance)
    syms = ["XAUUSD", "BTCUSD", "BRENT", "ETHUSD", "WTI", "COPPER", "XLE", "XLK"]
    t = time.perf_counter()
    out = price.get_quotes(syms)
    elapsed = time.perf_counter() - t
    assert [q.symbol for q in out] == syms
    assert [q.price for q in out] == [float(len(s)) for s in syms]
    assert seen_threads["BTCUSD"] == seen_threads["ETHUSD"]  # CoinGecko tek işte
    assert elapsed < 0.05 * len(syms) * 0.6  # sıralıdan belirgin hızlı


def test_snapshot_parts_are_recorded():
    from packages.data.ingestion import pipeline

    pipeline.build_snapshot()
    parts = pipeline.last_snapshot_parts()
    assert {"prices", "news", "calendar", "macro", "rotation", "derivatives", "technical"} <= set(parts)
    assert all(v >= 0 for v in parts.values())
