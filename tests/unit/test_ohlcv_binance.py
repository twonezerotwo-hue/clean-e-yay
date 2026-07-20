"""Binance OHLCV provider (kripto gerçek-fitil kaynağı, BINANCE_OHLCV_ENABLED).

Hepsi offline (urlopen/provider monkeypatch'lenir). Kapsam:
- Ticker eşleme (statik map + USD/USDT soneki heuristiği).
- Kline parse: gerçek fitil (high>close, low<open), hacim, source damgası.
- Host fallback (451 geo-engel → mirror) ve unlisted (-1121) negatif cache.
- Orchestrator rotası: flag OFF → bayt-aynı CoinGecko yolu (binance'e hiç
  gidilmez); flag ON → binance önce, başarısızlıkta CoinGecko'ya düşüş.
- 4h: flag ON → NATIVE binance (resample değil); binance düşerse eski
  resample:1h yolu.
- Bar arşivi: flag ON + BAR_HISTORY_ENABLED → arşive binance-damgalı gerçek
  fitilli KAPANMIŞ barlar girer (son/oluşan bar girmez).
"""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.ohlcv import binance

_BASE_TS = datetime(2026, 6, 1, tzinfo=UTC)


def _kline_rows(n: int, *, step_hours: int = 1) -> list[list]:
    """Binance kline formatında satırlar (fiyat alanları string döner)."""
    rows = []
    for i in range(n):
        ts_ms = int((_BASE_TS + timedelta(hours=i * step_hours)).timestamp() * 1000)
        o = 100.0 + i
        rows.append([
            ts_ms, f"{o}", f"{o + 5.0}", f"{o - 3.0}", f"{o + 1.0}", f"{10.0 + i}",
            ts_ms + step_hours * 3600 * 1000 - 1, "0", 42, "0", "0", "0",
        ])
    return rows


@pytest.fixture(autouse=True)
def _clean_unlisted():
    with binance._UNLISTED_LOCK:
        binance._UNLISTED.clear()
    yield
    with binance._UNLISTED_LOCK:
        binance._UNLISTED.clear()


# ---------------- ticker eşleme ----------------

def test_ticker_mapping_static_and_heuristic() -> None:
    assert binance._ticker_for("BTCUSD") == "BTCUSDT"
    assert binance._ticker_for("ETHUSD") == "ETHUSDT"
    assert binance._ticker_for("DODO") == "DODOUSDT"       # sonek yok → +USDT
    assert binance._ticker_for("SKYAI") == "SKYAIUSDT"
    assert binance._ticker_for("SOLUSD") == "SOLUSDT"       # USD → USDT
    assert binance._ticker_for("SOLUSDT") == "SOLUSDT"      # zaten USDT → dupe yok


# ---------------- kline parse ----------------

def test_get_bars_parses_real_wicks_and_volume(monkeypatch) -> None:
    monkeypatch.setattr(binance, "_fetch_klines", lambda t, i, n: _kline_rows(5))
    bars = binance.get_bars("BTCUSD", "1h")
    assert bars is not None and len(bars) == 5
    b = bars[0]
    assert b.ts == _BASE_TS
    assert (b.open, b.high, b.low, b.close) == (100.0, 105.0, 97.0, 101.0)
    assert b.high > max(b.open, b.close)  # gerçek fitil — o=h=l=c DEĞİL
    assert b.low < min(b.open, b.close)
    assert b.volume == 10.0
    assert b.source == "binance" and b.verified is True
    assert b.timeframe == "1h" and b.symbol == "BTCUSD"


def test_get_bars_unsupported_tf_and_fetch_failure(monkeypatch) -> None:
    assert binance.get_bars("BTCUSD", "5m") is None
    monkeypatch.setattr(binance, "_fetch_klines", lambda t, i, n: None)
    assert binance.get_bars("BTCUSD", "1h") is None


def test_native_tfs_include_4h_and_1w() -> None:
    assert {"15m", "1h", "4h", "1d", "1w"} == set(binance.NATIVE_TFS)


# ---------------- host fallback + unlisted negatif cache ----------------

class _FakeResp:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_klines_host_fallback_on_451(monkeypatch) -> None:
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):
        seen.append(req.full_url)
        if "api.binance.com" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 451, "blocked", None, io.BytesIO(b""))
        return _FakeResp(_kline_rows(3))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    rows = binance._fetch_klines("BTCUSDT", "1h", 100)
    assert rows is not None and len(rows) == 3
    assert len(seen) == 2 and "data-api.binance.vision" in seen[1]


def test_unlisted_symbol_negative_cached(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        body = json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode()
        raise urllib.error.HTTPError(req.full_url, 400, "bad request", None, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert binance.get_bars("SKYAI", "1h") is None
    assert calls["n"] == 1  # -1121 ilk host'ta kesin cevap — mirror denenmez
    assert binance.get_bars("SKYAI", "1h") is None
    assert calls["n"] == 1  # negatif cache: yeniden istek atılmadı


# ---------------- orchestrator rotası ----------------

@pytest.fixture
def runtime_ohlcv(monkeypatch, tmp_path):
    """Fixture modunu kapat, cache'i boş tmp dizinine al (test_ohlcv_technicals
    ile aynı desen)."""
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("OHLCV_USE_FIXTURE", raising=False)
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(tmp_path / "ohlcv"))
    from packages.data.providers import ohlcv
    ohlcv.reset_provider_status()
    return ohlcv


def _fake_binance_bars(symbol: str, tf: str, n: int = 60):
    from packages.data.types import OHLCVBar
    step = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24, "1w": 168}[tf]
    return [
        OHLCVBar(
            symbol=symbol, timeframe=tf,
            ts=_BASE_TS + timedelta(hours=i * step),
            open=100.0 + i, high=106.0 + i, low=96.0 + i, close=101.0 + i,
            volume=5.0, source="binance", verified=True,
        )
        for i in range(n)
    ]


def test_flag_off_binance_never_called(runtime_ohlcv, monkeypatch) -> None:
    called = {"binance": 0}

    def boom(s, tf):
        called["binance"] += 1
        raise AssertionError("flag OFF iken binance çağrılmamalı")

    monkeypatch.setattr(runtime_ohlcv.binance, "get_bars", boom)
    monkeypatch.setattr(
        runtime_ohlcv.coingecko, "get_bars",
        lambda s, tf: _fake_binance_bars(s, tf, 30),
    )
    bars = runtime_ohlcv.get_bars("BTCUSD", "1h")
    assert len(bars) == 30 and called["binance"] == 0


def test_flag_on_binance_preferred(runtime_ohlcv, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setattr(
        runtime_ohlcv.binance, "get_bars",
        lambda s, tf: _fake_binance_bars(s, tf, 40),
    )
    monkeypatch.setattr(
        runtime_ohlcv.coingecko, "get_bars",
        lambda s, tf: pytest.fail("binance başarılıyken coingecko'ya gidilmemeli"),
    )
    bars = runtime_ohlcv.get_bars("BTCUSD", "1h")
    assert len(bars) == 40 and bars[0].source == "binance"
    status = runtime_ohlcv.get_provider_status()
    assert status["ohlcv_binance"]["status"] == "ok"


def test_flag_on_falls_back_to_coingecko(runtime_ohlcv, monkeypatch) -> None:
    from packages.data.providers.ohlcv import fixtures
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setattr(runtime_ohlcv.binance, "get_bars", lambda s, tf: None)
    monkeypatch.setattr(
        runtime_ohlcv.coingecko, "get_bars",
        lambda s, tf: fixtures.get_bars(s, tf, n=25),
    )
    bars = runtime_ohlcv.get_bars("BTCUSD", "1h")
    assert len(bars) == 25
    status = runtime_ohlcv.get_provider_status()
    assert status["ohlcv_binance"]["status"] == "degraded"
    assert status["ohlcv_coingecko"]["status"] == "ok"


def test_flag_on_yfinance_route_untouched(runtime_ohlcv, monkeypatch) -> None:
    """Kripto-dışı semboller flag ON'ken de yfinance'ta kalır (binance kripto
    evreniyle sınırlı)."""
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setattr(
        runtime_ohlcv.binance, "get_bars",
        lambda s, tf: pytest.fail("yfinance sembolü binance'e yönlenmemeli"),
    )
    monkeypatch.setattr(
        runtime_ohlcv.yfinance, "get_bars",
        lambda s, tf: _fake_binance_bars(s, tf, 20),
    )
    bars = runtime_ohlcv.get_bars("XAUUSD", "1h")
    assert len(bars) == 20


def test_flag_on_4h_native_from_binance(runtime_ohlcv, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setattr(
        runtime_ohlcv.binance, "get_bars",
        lambda s, tf: _fake_binance_bars(s, tf, 50),
    )
    bars = runtime_ohlcv.get_bars("BTCUSD", "4h")
    assert bars and bars[0].timeframe == "4h"
    assert bars[0].source == "binance"  # NATIVE — resampled:1h DEĞİL


def test_flag_on_4h_falls_back_to_resample(runtime_ohlcv, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setattr(
        runtime_ohlcv.binance,
        "get_bars",
        lambda s, tf: _fake_binance_bars(s, tf, 120) if tf == "1h" else None,
    )
    bars = runtime_ohlcv.get_bars("BTCUSD", "4h")
    assert bars and bars[0].timeframe == "4h"
    assert bars[0].source == "resampled:1h"  # eski yol korunur


# ---------------- bar arşivi entegrasyonu ----------------

def test_archive_accumulates_real_wick_binance_bars(
    runtime_ohlcv, monkeypatch, tmp_path
) -> None:
    from packages.data.providers.ohlcv import history
    monkeypatch.setenv("BINANCE_OHLCV_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_ENABLED", "1")
    monkeypatch.setenv("BAR_HISTORY_DIR", str(tmp_path / "bar_history"))
    history._LAST_TS.clear()
    fake = _fake_binance_bars("BTCUSD", "1h", 10)
    monkeypatch.setattr(runtime_ohlcv.binance, "get_bars", lambda s, tf: fake)
    runtime_ohlcv.get_bars("BTCUSD", "1h")
    archived = history.load("BTCUSD", "1h")
    assert len(archived) == 9  # son (oluşan) bar arşive girmez
    assert all(b.source == "binance" for b in archived)
    assert all(b.high > max(b.open, b.close) for b in archived)  # gerçek fitil
    history._LAST_TS.clear()
