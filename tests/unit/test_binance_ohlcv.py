"""Binance spot gerçek mum kaynağı (owner kararı 2026-10-30) — offline.

- Yalnız kapanmış mumlar; bozuk satırlar atılır; 200 bardan azsa kaynak sayılmaz.
- Bayrak kapalıyken hiç devreye girmez; özel kripto varlık SEMBOLUSDT çiftine eşlenir.
- Listelenmeyen sembol (HTTP 400) bir gün yeniden sorulmaz.
- Router: Kraken düşerse Binance, DODO gibi varlıkta CoinGecko'dan önce Binance.
"""
from __future__ import annotations

import io
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import ohlcv
from packages.data.providers.ohlcv import binance, coingecko, kraken
from packages.data.registry import custom_assets


def _rows(count: int, minutes: int, *, unfinished: bool = True):
    now = datetime.now(UTC)
    start = now - timedelta(minutes=(count + 2) * minutes)
    rows = []
    for i in range(count + (1 if unfinished else 0)):
        ts = start + timedelta(minutes=i * minutes)
        if unfinished and i == count:
            ts = now - timedelta(minutes=1)  # henüz kapanmadı
        rows.append([int(ts.timestamp() * 1000), "100", "110", "90", "105", "12.5", 0, "0", 1, "0", "0", "0"])
    return rows


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(tmp_path / "ohlcv"))
    monkeypatch.setenv("EYAY_BINANCE_OHLCV_ENABLED", "true")
    monkeypatch.delenv("EYAY_KRAKEN_OHLCV_ENABLED", raising=False)
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("OHLCV_USE_FIXTURE", raising=False)
    binance.reset_cache()
    ohlcv.reset_provider_status()
    yield
    binance.reset_cache()


def test_parse_drops_unfinished_and_invalid():
    rows = _rows(3, 15)
    rows.insert(1, [rows[0][0] + 1, "100", "80", "90", "105", "1"])  # high < close: bozuk
    bars = binance._parse(rows, "BTCUSD", "15m")
    assert len(bars) == 3
    assert all(b.source == "binance_spot" and b.verified for b in bars)


def test_flag_and_pair_mapping(monkeypatch):
    monkeypatch.setattr(custom_assets, "ticker_for", lambda s, p: "dodo" if (s, p) == ("DODO", "coingecko") else None)
    assert binance.pair_for("BTCUSD") == "BTCUSDT"
    assert binance.pair_for("DODO") == "DODOUSDT"
    assert binance.pair_for("XAUUSD") is None
    monkeypatch.setenv("EYAY_BINANCE_OHLCV_ENABLED", "false")
    assert not binance.enabled_for("BTCUSD")


def test_insufficient_history_is_not_a_source(monkeypatch):
    monkeypatch.setattr(binance, "_fetch", lambda pair, tf: _rows(50, 60))
    assert binance.get_bars("BTCUSD", "1h") is None


def test_unlisted_symbol_is_skipped_for_a_day(monkeypatch):
    calls = []

    def boom(pair, tf):
        calls.append(pair)
        raise urllib.error.HTTPError("u", 400, "Invalid symbol", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(binance, "_fetch", boom)
    assert binance.get_bars("ETHUSD", "1h") is None
    assert not binance.enabled_for("ETHUSD")
    assert binance.get_bars("ETHUSD", "1h") is None
    assert calls == ["ETHUSDT"]


def test_router_uses_binance_when_kraken_fails(monkeypatch):
    monkeypatch.setenv("EYAY_KRAKEN_OHLCV_ENABLED", "true")
    monkeypatch.setattr(kraken, "get_bars", lambda s, tf: None)
    monkeypatch.setattr(binance, "_fetch", lambda pair, tf: _rows(300, 60))
    monkeypatch.setattr(coingecko, "get_bars", lambda s, tf: pytest.fail("CoinGecko'ya düşülmemeli"))
    bars = ohlcv._native_bars("BTCUSD", "1h")
    assert len(bars) == 300 and bars[-1].source == "binance_spot"
    assert ohlcv.get_provider_status()["ohlcv_binance"]["status"] == "ok"


def test_router_prefers_binance_over_coingecko_for_custom_crypto(monkeypatch):
    monkeypatch.setattr(custom_assets, "ticker_for", lambda s, p: "dodo" if (s, p) == ("DODO", "coingecko") else None)
    monkeypatch.setattr(binance, "_fetch", lambda pair, tf: _rows(250, 15))
    monkeypatch.setattr(coingecko, "get_bars", lambda s, tf: pytest.fail("CoinGecko çağrılmamalı"))
    bars = ohlcv._native_bars("DODO", "15m")
    assert bars and all(b.source == "binance_spot" for b in bars)


def test_coingecko_path_ignores_binance_cache(monkeypatch):
    # Binance düştüğünde CoinGecko yolu Binance önbelleğini kendi adıyla sunmaz.
    monkeypatch.setattr(custom_assets, "ticker_for", lambda s, p: "dodo" if (s, p) == ("DODO", "coingecko") else None)
    monkeypatch.setattr(binance, "_fetch", lambda pair, tf: _rows(250, 15))
    assert ohlcv._native_bars("DODO", "15m")
    monkeypatch.setattr(binance, "_fetch", lambda pair, tf: (_ for _ in ()).throw(OSError("ağ")))
    monkeypatch.setattr(coingecko.SUPPORTED, "__contains__", lambda self, s: s == "DODO", raising=False)
    seen = []
    monkeypatch.setattr(coingecko, "get_bars", lambda s, tf: seen.append(s) or None)
    ohlcv._native_bars("DODO", "15m")  # taze Binance önbelleği yine Binance'ten döner
    assert seen == []
