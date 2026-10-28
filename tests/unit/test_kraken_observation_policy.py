"""Kraken observation-time and rollback regressions."""
from datetime import UTC, datetime, timedelta

from packages.data.providers import ohlcv
from packages.data.providers.technical import (
    compute_snapshot,
    staleness_age_sec,
)
from packages.data.providers.technical.observation import observed_at
from packages.data.types import OHLCVBar


def bars(source, verified=True, count=230):
    last = datetime(2026, 10, 12, tzinfo=UTC)
    out = []
    for i in range(count):
        price = 100 + i * 0.03 + (i % 7) * 0.2
        out.append(OHLCVBar(
            symbol="BTCUSD",
            timeframe="1w",
            ts=last - timedelta(weeks=count - 1 - i),
            open=price,
            high=price + 3,
            low=price - 3,
            close=price + 1,
            volume=100,
            source=source,
            verified=verified,
        ))
    return out


def test_weekly_kraken_uses_close_timestamp():
    data = bars("kraken_spot")
    assert observed_at(data, "1w") == datetime(
        2026, 10, 19, tzinfo=UTC
    )


def test_old_provider_timestamp_unchanged():
    data = bars("coingecko")
    assert observed_at(data, "1w") == data[-1].ts


def test_unverified_candle_does_not_gain_freshness():
    data = bars("kraken_spot", verified=False)
    assert observed_at(data, "1w") == data[-1].ts


def test_weekly_snapshot_is_fresh_sunday():
    data = bars("kraken_spot")
    now = datetime(2026, 10, 25, 12, tzinfo=UTC)
    snap = compute_snapshot("BTCUSD", "1w", data, now=now)
    assert snap.ts == datetime(2026, 10, 19, tzinfo=UTC)
    assert staleness_age_sec(snap, now=now) is None


def test_weekly_snapshot_eventually_expires():
    data = bars("kraken_spot")
    now = datetime(2026, 11, 1, tzinfo=UTC)
    snap = compute_snapshot("BTCUSD", "1w", data, now=now)
    assert snap.status == "DEGRADED"
    assert staleness_age_sec(snap, now=now) is not None


def test_kraken_cache_not_reused_when_disabled(monkeypatch):
    monkeypatch.setenv("EYAY_KRAKEN_OHLCV_ENABLED", "false")
    kraken_bar = bars("kraken_spot")[-1]
    kraken_bar.timeframe = "15m"

    coingecko_bar = kraken_bar.model_copy(
        update={"source": "resampled:coingecko_5m"}
    )

    monkeypatch.setattr(
        ohlcv.cache,
        "load",
        lambda *args: ohlcv.cache.CachedBars(
            bars=[kraken_bar], age_seconds=0
        ),
    )
    monkeypatch.setattr(
        ohlcv.cache, "save", lambda *args: None
    )
    monkeypatch.setattr(
        ohlcv.coingecko,
        "get_bars",
        lambda symbol, tf: [coingecko_bar],
    )

    result = ohlcv._native_bars("BTCUSD", "15m")
    assert result[0].source == "resampled:coingecko_5m"
