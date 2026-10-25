"""Verified Kraken OHLCV and custom crypto market sessions."""

from datetime import UTC, datetime, timedelta

from packages.data.providers import ohlcv
from packages.data.providers.ohlcv import kraken
from packages.data.registry import custom_assets
from packages.data.types import OHLCVBar
from packages.market_sessions.config import load_config


def _payload(count, interval):
    now = datetime.now(UTC)

    start = now - timedelta(
        minutes=(count + 3) * interval
    )

    rows = []

    for i in range(count + 1):
        ts = start + timedelta(minutes=i * interval)
        rows.append([
            int(ts.timestamp()),
            "100",
            "110",
            "90",
            "105",
            "102",
            "2.5",
            10,
        ])

    return {
        "error": [],
        "result": {
            "PAIR": rows,
            "last": 0,
        },
    }


def test_real_15m_candles(monkeypatch):
    monkeypatch.setenv(
        "EYAY_KRAKEN_OHLCV_ENABLED", "true"
    )

    monkeypatch.setattr(
        kraken,
        "_fetch",
        lambda symbol, timeframe: _payload(240, 15),
    )

    bars = kraken.get_bars("BTCUSD", "15m")

    assert bars is not None
    assert len(bars) == 240
    assert all(b.verified for b in bars)
    assert all(b.source == "kraken_spot" for b in bars)
    assert all(b.high > b.low for b in bars)


def test_real_weekly_candles(monkeypatch):
    monkeypatch.setenv(
        "EYAY_KRAKEN_OHLCV_ENABLED", "true"
    )

    monkeypatch.setattr(
        kraken,
        "_fetch",
        lambda symbol, timeframe: _payload(230, 10080),
    )

    bars = kraken.get_bars("ETHUSD", "1w")

    assert bars is not None
    assert len(bars) == 230


def test_insufficient_history_fails_closed(monkeypatch):
    monkeypatch.setenv(
        "EYAY_KRAKEN_OHLCV_ENABLED", "true"
    )

    monkeypatch.setattr(
        kraken,
        "_fetch",
        lambda symbol, timeframe: _payload(100, 15),
    )

    assert kraken.get_bars("BTCUSD", "15m") is None


def test_invalid_ohlc_rejected():
    payload = _payload(3, 15)

    payload["result"]["PAIR"][0][1] = "200"
    payload["result"]["PAIR"][0][2] = "100"

    bars = kraken._parse(
        payload, "BTCUSD", "15m"
    )

    assert len(bars) == 2


def test_unfinished_candle_excluded():
    payload = _payload(2, 15)

    bars = kraken._parse(
        payload, "BTCUSD", "15m"
    )

    assert len(bars) == 2


def test_provider_requires_explicit_activation(monkeypatch):
    monkeypatch.delenv(
        "EYAY_KRAKEN_OHLCV_ENABLED",
        raising=False,
    )

    assert not kraken.enabled_for("BTCUSD")

    monkeypatch.setenv(
        "EYAY_KRAKEN_OHLCV_ENABLED", "true"
    )

    assert kraken.enabled_for("BTCUSD")
    assert kraken.enabled_for("ETHUSD")
    assert not kraken.enabled_for("DODO")


def test_ohlcv_routing(monkeypatch):
    monkeypatch.setenv(
        "EYAY_KRAKEN_OHLCV_ENABLED", "true"
    )

    monkeypatch.setenv("TEST_USE_MOCK", "false")
    monkeypatch.setenv("OHLCV_USE_FIXTURE", "false")

    now = datetime.now(UTC)

    bars = [
        OHLCVBar(
            symbol="BTCUSD",
            timeframe="15m",
            ts=now - timedelta(minutes=(220-i)*15),
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1,
            source="kraken_spot",
            verified=True,
        )
        for i in range(220)
    ]

    monkeypatch.setattr(
        ohlcv.cache, "load", lambda *a: None
    )

    monkeypatch.setattr(
        ohlcv.cache, "save", lambda *a: None
    )

    monkeypatch.setattr(
        ohlcv.history, "append_new", lambda *a: 0
    )

    monkeypatch.setattr(
        kraken,
        "get_bars",
        lambda symbol, tf: bars,
    )

    result = ohlcv.get_bars("BTCUSD", "15m")

    assert len(result) == 220
    assert all(x.source == "kraken_spot" for x in result)


def test_dynamic_crypto_session(monkeypatch):
    asset = custom_assets.CustomAsset(
        symbol="DODO",
        label="DODO",
        provider="coingecko",
        ticker="dodo",
    )

    monkeypatch.setattr(
        custom_assets,
        "get",
        lambda code: asset if code == "DODO" else None,
    )

    cfg = load_config()

    market = cfg.markets_for_asset("DODO")

    assert len(market) == 1
    assert market[0].market_id == "CRYPTO_GLOBAL"


def test_unknown_asset_keeps_restrictive_session(monkeypatch):
    monkeypatch.setattr(
        custom_assets,
        "get",
        lambda code: None,
    )

    cfg = load_config()

    assert cfg.markets_for_asset("UNKNOWN_TEST") == ()
