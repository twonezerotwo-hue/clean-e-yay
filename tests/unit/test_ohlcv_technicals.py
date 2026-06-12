"""T1 — OHLCV provider + gerçek multi-timeframe technicals testleri.

Hepsi offline: live network yok (provider'lar monkeypatch'lenir, test
modu fixture barları kullanır).

- Fixture OHLCV ile RSI/MACD/ATR/EMA gerçek hesap doğruluğu.
- Resample doğruluğu (4h = 1h×4, 1w = ISO hafta).
- Yetersiz bar → alanlar None + DEGRADED, crash yok.
- TF bazlı stale kuralı → DEGRADED.
- Pipeline technicals_by_tf 5 TF doldurur; legacy `technicals` 1d'den
  beslenir.
- Disk cache: TTL içinde provider'a gidilmez; live fail → stale cache.
- Runtime'da fixture bar ASLA dönmez (DATA_POLICY).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.ohlcv import fixtures, resample
from packages.data.providers.technical import compute_snapshot, indicators
from packages.data.types import OHLCVBar


def _bar(symbol: str, tf: str, ts: datetime, o: float, h: float, lo: float,
         c: float, v: float | None = None) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol, timeframe=tf, ts=ts,
        open=o, high=h, low=lo, close=c, volume=v,
        source="test", verified=True,
    )


def _flat_bars(n: int, price: float = 100.0, tf: str = "1d") -> list[OHLCVBar]:
    start = datetime.now(UTC) - timedelta(days=n)
    return [
        _bar("BTCUSD", tf, start + timedelta(days=i), price, price, price, price)
        for i in range(n)
    ]


# ---------------- indikatörler ----------------

def test_rsi_monotonic_extremes() -> None:
    up = [100.0 + i for i in range(30)]
    down = [100.0 - i for i in range(30)]
    assert indicators.rsi(up) == 100.0
    assert indicators.rsi(down) == 0.0


def test_rsi_mixed_series_in_open_interval() -> None:
    closes = [100 + (3 if i % 2 == 0 else -2) * (i % 5 + 1) * 0.1 for i in range(40)]
    v = indicators.rsi(closes)
    assert v is not None and 0.0 < v < 100.0


def test_rsi_insufficient_returns_none() -> None:
    assert indicators.rsi([100.0] * 10) is None


def test_ema_constant_series_equals_value() -> None:
    assert indicators.ema([5.0] * 50, 20) == pytest.approx(5.0)


def test_macd_constant_series_is_zero() -> None:
    out = indicators.macd([10.0] * 60)
    assert out is not None
    macd_line, _signal_line, hist = out
    assert macd_line == pytest.approx(0.0, abs=1e-9)
    assert hist == pytest.approx(0.0, abs=1e-9)


def test_macd_insufficient_returns_none() -> None:
    assert indicators.macd([10.0] * 33) is None  # slow+signal-1 = 34 gerekir


def test_atr_flat_bars_zero_and_insufficient_none() -> None:
    bars = _flat_bars(20)
    assert indicators.atr(bars) == pytest.approx(0.0)
    assert indicators.atr(bars[:10]) is None


# ---------------- resample ----------------

def test_resample_1h_to_4h_aggregation() -> None:
    base = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
    bars = []
    for i in range(8):
        bars.append(_bar(
            "XAUUSD", "1h", base + timedelta(hours=i),
            o=100.0 + i, h=110.0 + i, lo=90.0 + i, c=105.0 + i, v=10.0,
        ))
    out = resample.resample(bars, "4h")
    assert len(out) == 2
    first, second = out
    assert first.ts == base
    assert first.open == 100.0          # ilk barın open'ı
    assert first.high == 113.0          # max(high[0..3])
    assert first.low == 90.0            # min(low[0..3])
    assert first.close == 108.0         # son barın close'u
    assert first.volume == 40.0
    assert first.timeframe == "4h"
    assert first.source == "resampled:1h"
    assert second.ts == base + timedelta(hours=4)
    assert second.close == 112.0


def test_resample_1d_to_1w_iso_week_buckets() -> None:
    monday = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)  # Pazartesi
    bars = [
        _bar("BTCUSD", "1d", monday + timedelta(days=i),
             o=100.0, h=101.0, lo=99.0, c=100.5)
        for i in range(8)  # Pzt..Pzt (ikinci hafta 1 bar)
    ]
    out = resample.resample(bars, "1w")
    assert len(out) == 2
    assert out[0].ts == monday
    assert out[1].ts == monday + timedelta(days=7)
    assert out[0].source == "resampled:1d"


# ---------------- compute_snapshot ----------------

def test_insufficient_bars_yields_none_fields_degraded() -> None:
    snap = compute_snapshot("BTCUSD", "1h", _flat_bars(5, tf="1h"))
    assert snap.rsi is None
    assert snap.macd is None
    assert snap.atr is None
    assert snap.ema_stack is None
    assert snap.score == 50.0
    assert snap.status == "DEGRADED"
    assert snap.bars_used == 5


def test_no_bars_no_crash_degraded_neutral() -> None:
    snap = compute_snapshot("BTCUSD", "15m", [])
    assert snap.status == "DEGRADED"
    assert snap.score == 50.0
    assert snap.source == "none"
    assert snap.bars_used == 0


def test_stale_bars_marked_degraded_per_tf() -> None:
    # 15m: 30 dk eşiği — 2 saat eski son bar DEGRADED olmalı.
    bars = fixtures.get_bars("BTCUSD", "15m")
    now = bars[-1].ts + timedelta(hours=2)
    snap = compute_snapshot("BTCUSD", "15m", bars, now=now)
    assert snap.status == "DEGRADED"
    # 1d: 48 sa eşiği — aynı yaş 1d için taze sayılır.
    bars_1d = fixtures.get_bars("BTCUSD", "1d")
    snap_1d = compute_snapshot(
        "BTCUSD", "1d", bars_1d, now=bars_1d[-1].ts + timedelta(hours=2)
    )
    assert snap_1d.status == "OK"


def test_fixture_bars_produce_full_snapshot() -> None:
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        bars = fixtures.get_bars("BTCUSD", tf)
        snap = compute_snapshot("BTCUSD", tf, bars)
        assert snap.timeframe == tf
        assert snap.rsi is not None and 0 <= snap.rsi <= 100
        assert snap.macd is not None
        assert snap.atr is not None and snap.atr >= 0
        assert snap.ema_stack in {"bullish", "bearish", "mixed"}
        assert 0 <= snap.score <= 100
        assert snap.status == "OK"


# ---------------- pipeline ----------------

def test_pipeline_fills_technicals_by_tf_and_legacy_1d() -> None:
    from packages.data.ingestion.pipeline import build_snapshot

    snap = build_snapshot(["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "VIX"])
    assert snap.technicals_by_tf is not None
    # multi-TF yalnızca ana 4 sembol için; VIX legacy 1d alır.
    assert set(snap.technicals_by_tf.keys()) == {"BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"}
    for by_tf in snap.technicals_by_tf.values():
        assert set(by_tf.keys()) == {"15m", "1h", "4h", "1d", "1w"}
    # legacy alan 1d snapshot'ının kendisidir (geriye uyum).
    assert snap.technicals["BTCUSD"] is snap.technicals_by_tf["BTCUSD"]["1d"]
    assert snap.technicals["VIX"].timeframe == "1d"


# ---------------- runtime data policy ----------------

@pytest.fixture
def runtime_ohlcv(monkeypatch, tmp_path):
    """Fixture modunu kapat, cache'i boş tmp dizinine al."""
    monkeypatch.delenv("TEST_USE_MOCK", raising=False)
    monkeypatch.delenv("OHLCV_USE_FIXTURE", raising=False)
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(tmp_path / "ohlcv"))
    from packages.data.providers import ohlcv
    ohlcv.reset_provider_status()
    return ohlcv


def test_runtime_provider_failure_returns_empty_not_fixture(
    runtime_ohlcv, monkeypatch
) -> None:
    monkeypatch.setattr(runtime_ohlcv.coingecko, "get_bars", lambda s, tf: None)
    monkeypatch.setattr(runtime_ohlcv.yfinance, "get_bars", lambda s, tf: None)
    for sym in ("BTCUSD", "XAUUSD"):
        bars = runtime_ohlcv.get_bars(sym, "1h")
        assert bars == []  # fixture'a düşülmedi
    status = runtime_ohlcv.get_provider_status()
    assert status["ohlcv_coingecko"]["status"] == "degraded"


def test_runtime_failure_technicals_none_degraded(runtime_ohlcv, monkeypatch) -> None:
    monkeypatch.setattr(runtime_ohlcv.coingecko, "get_bars", lambda s, tf: None)
    monkeypatch.setattr(runtime_ohlcv.yfinance, "get_bars", lambda s, tf: None)
    from packages.data.providers import technical
    snap = technical.get_snapshot("BTCUSD", "1h")
    assert snap.rsi is None and snap.macd is None and snap.atr is None
    assert snap.status == "DEGRADED"
    assert snap.score == 50.0


def test_cache_hit_skips_provider_and_stale_fallback(
    runtime_ohlcv, monkeypatch, tmp_path
) -> None:
    calls = {"n": 0}

    def fake_fetch(symbol, tf):
        calls["n"] += 1
        return fixtures.get_bars(symbol, tf, n=60)  # gerçek-format bar üretimi

    monkeypatch.setattr(runtime_ohlcv.coingecko, "get_bars", fake_fetch)
    b1 = runtime_ohlcv.get_bars("BTCUSD", "1h")
    b2 = runtime_ohlcv.get_bars("BTCUSD", "1h")
    assert calls["n"] == 1  # ikinci çağrı TTL içinde cache'ten geldi
    assert len(b1) == len(b2) == 60

    # TTL'i bayatlat + provider'ı öldür → stale cache servis edilir.
    cache_file = tmp_path / "ohlcv" / "BTCUSD_1h.json"
    raw = json.loads(cache_file.read_text())
    raw["fetched_at"] = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    cache_file.write_text(json.dumps(raw))
    monkeypatch.setattr(runtime_ohlcv.coingecko, "get_bars", lambda s, tf: None)
    b3 = runtime_ohlcv.get_bars("BTCUSD", "1h")
    assert len(b3) == 60
    status = runtime_ohlcv.get_provider_status()
    assert status["ohlcv_coingecko"]["fallbacks"] >= 1


def test_resampled_tfs_derive_from_native(runtime_ohlcv, monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_ohlcv.coingecko,
        "get_bars",
        lambda s, tf: fixtures.get_bars(s, tf, n=120) if tf in ("1h", "1d") else None,
    )
    bars_4h = runtime_ohlcv.get_bars("BTCUSD", "4h")
    assert bars_4h and bars_4h[0].timeframe == "4h"
    assert bars_4h[0].source == "resampled:1h"
    bars_1w = runtime_ohlcv.get_bars("BTCUSD", "1w")
    assert bars_1w and bars_1w[0].timeframe == "1w"
    assert bars_1w[0].source == "resampled:1d"


# ---------------- endpoint ----------------

def test_data_snapshot_endpoint_includes_technicals_by_tf() -> None:
    from packages.data.ingestion import pipeline as pl
    pl._CACHE.clear()

    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    r = client.get("/api/v1/data/snapshot")
    assert r.status_code == 200
    body = r.json()
    tbt = body["technicals_by_tf"]
    assert "BTCUSD" in tbt
    one = tbt["BTCUSD"]["1d"]
    assert one["status"] in {"OK", "DEGRADED"}
    assert isinstance(one["score"], (int, float))
    assert set(tbt["BTCUSD"].keys()) == {"15m", "1h", "4h", "1d", "1w"}
