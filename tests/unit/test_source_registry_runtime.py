"""Source registry must describe the feeds/providers the runtime actually uses."""
from __future__ import annotations

from pathlib import Path

import yaml

from packages.data.providers.news import rss
from packages.data.providers.ohlcv import cache as ohlcv_cache
from packages.discovery import scanner

ROOT = Path(__file__).resolve().parents[2]


def test_source_registry_runtime_inventory_matches_modules() -> None:
    registry = yaml.safe_load(
        (ROOT / "config" / "source_registry_v1.0.yaml").read_text(encoding="utf-8")
    )
    inventory = registry["runtime_inventory"]
    discovery = scanner.load_config()

    assert inventory["news"]["market_rss"]["count"] == len(rss.MARKET_FEEDS)
    assert inventory["news"]["geo_rss"]["count"] == len(rss.GEO_FEEDS)
    assert inventory["news"]["discovery_topic_feeds"]["count"] == len(
        (discovery.get("news_discovery") or {}).get("extra_feeds") or []
    )
    assert set(inventory["providers"]["ohlcv"]) == {
        "ohlcv_kraken",
        "ohlcv_binance",
        "ohlcv_coingecko",
        "ohlcv_yfinance",
    }
    assert inventory["providers"]["derivatives"] == ["derivatives_binance"]
    assert inventory["providers"]["options"] == ["options_deribit"]

    source_ids = {row["id"] for row in registry["sources"]}
    for provider in (
        *inventory["providers"]["ohlcv"],
        *inventory["providers"]["derivatives"],
        *inventory["providers"]["options"],
    ):
        assert any(provider in source_id for source_id in source_ids), provider


def test_coingecko_disk_cache_respects_provider_throttle_window(monkeypatch) -> None:
    monkeypatch.setenv("COINGECKO_OHLCV_TTL_SEC", "2400")
    bar = type("Bar", (), {"timeframe": "15m", "source": "coingecko"})()
    assert ohlcv_cache.CachedBars([bar], age_seconds=1200).fresh
    assert not ohlcv_cache.CachedBars([bar], age_seconds=2400).fresh
