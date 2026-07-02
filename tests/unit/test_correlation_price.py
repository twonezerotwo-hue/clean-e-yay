"""F2-2 — fiyat-getirisi korelasyonu (computed_price) testleri.

- Flag KAPALI (default): aktif rho zinciri eski davranışla birebir (computed →
  baseline → neutral); fiyat-rho yalnız `rho_price`/`price_samples` gözlem
  alanlarında.
- Flag AÇIK: yeterli ortak günü olan çiftte computed_price zincirin başına
  geçer; yetersizse eski zincir devralır.
- DATA_POLICY: verified=False (fixture) barlar seriye girmez.
- Pencere deterministik: veri setindeki en son bar gününe göre.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.ohlcv import cache as ohlcv_cache
from packages.data.registry.loader import threshold_override
from packages.data.types import OHLCVBar
from packages.risk import correlation as corr

_FLAG_ON = {"risk_gates": {"correlation_price_returns": True}}


def _bars(symbol: str, closes: list[float], *, verified: bool = True) -> list[OHLCVBar]:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    return [
        OHLCVBar(
            symbol=symbol, timeframe="1d", ts=start + timedelta(days=i),
            open=c, high=c, low=c, close=c, volume=1.0,
            source="test", verified=verified,
        )
        for i, c in enumerate(closes)
    ]


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(tmp_path))
    return tmp_path


# 25 bar → 24 getiri; y = x'in ölçeklisi (rho=+1), z = tersi (rho=-1)
_X = [100.0 + i + (3.0 if i % 2 == 0 else -3.0) for i in range(25)]
_Y = [2 * v for v in _X]
_Z = [400.0 - v for v in _X]


def test_price_series_and_pair_rho(cache_dir) -> None:
    ohlcv_cache.save("AAA", "1d", _bars("AAA", _X))
    ohlcv_cache.save("BBB", "1d", _bars("BBB", _Y))
    ohlcv_cache.save("CCC", "1d", _bars("CCC", _Z))
    series = corr.price_return_series(["AAA", "BBB", "CCC"])
    assert len(series["AAA"]) == 24
    rho_ab, n_ab = corr._pair_price_rho("AAA", "BBB", series)
    rho_ac, _ = corr._pair_price_rho("AAA", "CCC", series)
    assert n_ab == 24
    assert rho_ab == pytest.approx(1.0, abs=1e-6)
    # 400−x afin dönüşümü yüzde-getiride tam −1 vermez (payda farklı) → ~−0.996
    assert rho_ac == pytest.approx(-1.0, abs=0.01)


def test_unverified_bars_excluded(cache_dir) -> None:
    """DATA_POLICY: fixture (verified=False) barlar seriye girmez."""
    ohlcv_cache.save("AAA", "1d", _bars("AAA", _X, verified=False))
    assert corr.price_return_series(["AAA"]) == {}


def test_flag_off_active_chain_unchanged_price_only_observed(cache_dir) -> None:
    """Flag kapalı: BTCUSD|ETHUSD aktif rho baseline'dan (0.75) gelir — eski
    davranış birebir; fiyat-rho yalnız gözlem alanında (+1'e yakın)."""
    ohlcv_cache.save("BTCUSD", "1d", _bars("BTCUSD", _X))
    ohlcv_cache.save("ETHUSD", "1d", _bars("ETHUSD", _Y))
    entries = corr.matrix(["BTCUSD", "ETHUSD"], trades=[])
    e = entries[0]
    assert e.source == "baseline"
    assert e.rho == pytest.approx(0.75)
    assert e.rho_price == pytest.approx(1.0, abs=1e-6)
    assert e.price_samples == 24


def test_flag_on_price_takes_priority(cache_dir) -> None:
    ohlcv_cache.save("BTCUSD", "1d", _bars("BTCUSD", _X))
    ohlcv_cache.save("ETHUSD", "1d", _bars("ETHUSD", _Z))  # ters seri → rho=-1
    with threshold_override(_FLAG_ON):
        entries = corr.matrix(["BTCUSD", "ETHUSD"], trades=[])
    e = entries[0]
    assert e.source == "computed_price"
    assert e.rho == pytest.approx(-1.0, abs=0.01)  # baseline +0.75'i ezdi
    assert e.samples == 24


def test_flag_on_insufficient_overlap_falls_back(cache_dir) -> None:
    """Ortak gün < correlation_price_min_overlap_days (20) → fiyat-rho aktif
    OLAMAZ; zincir baseline'a düşer, gözlemde price_samples görünür."""
    ohlcv_cache.save("BTCUSD", "1d", _bars("BTCUSD", _X[:10]))
    ohlcv_cache.save("ETHUSD", "1d", _bars("ETHUSD", _Y[:10]))
    with threshold_override(_FLAG_ON):
        entries = corr.matrix(["BTCUSD", "ETHUSD"], trades=[])
    e = entries[0]
    assert e.source == "baseline"
    assert e.rho == pytest.approx(0.75)
    assert e.rho_price is None
    assert e.price_samples == 9


def test_flag_on_no_cache_neutral_fallback(cache_dir) -> None:
    """Cache yok + baseline yok → neutral (rho=0) — eski davranış korunur."""
    with threshold_override(_FLAG_ON):
        entries = corr.matrix(["AAA", "BBB"], trades=[])
    e = entries[0]
    assert e.source == "neutral"
    assert e.rho == 0.0
    assert e.rho_price is None


def test_window_filters_old_bars(cache_dir) -> None:
    """60 barlık seride yalnız son ~30 günün getirileri pencereye girer."""
    long_x = [100.0 + i for i in range(60)]
    ohlcv_cache.save("AAA", "1d", _bars("AAA", long_x))
    series = corr.price_return_series(["AAA"], window_days=30)
    assert 28 <= len(series["AAA"]) <= 31
