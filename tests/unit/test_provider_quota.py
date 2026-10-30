"""Ücretsiz sağlayıcı kotası: günlük ve dakikalık sınır, gün dönümü, kalıcılık."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import quota


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "quota.json"))
    quota.reset_cache()
    yield
    quota.reset_cache()


def _clock(start):
    state = {"t": start}
    return state, (lambda: state["t"])


def test_daily_limit_blocks_and_counts_denials(monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_TAVILY_PER_DAY", "2")
    st, now = _clock(datetime(2026, 10, 30, 10, 0, tzinfo=UTC))
    assert quota.consume("tavily", now=now)
    st["t"] += timedelta(minutes=5)
    assert quota.consume("tavily", now=now)
    st["t"] += timedelta(minutes=5)
    assert not quota.consume("tavily", now=now)
    row = quota.usage()["tavily"]
    assert row["count"] == 2 and row["denied"] == 1 and row["last_denied"] == "day"


def test_minute_limit_resets_next_minute(monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_TWELVEDATA_PER_MINUTE", "1")
    st, now = _clock(datetime(2026, 10, 30, 10, 0, 5, tzinfo=UTC))
    assert quota.consume("twelvedata", now=now)
    assert not quota.consume("twelvedata", now=now)
    st["t"] += timedelta(minutes=1)
    assert quota.consume("twelvedata", now=now)


def test_day_rollover_and_persistence(monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_ALPHAVANTAGE_PER_DAY", "1")
    monkeypatch.setenv("PROVIDER_QUOTA_ALPHAVANTAGE_PER_MINUTE", "0")
    st, now = _clock(datetime(2026, 10, 30, 23, 59, tzinfo=UTC))
    assert quota.consume("alphavantage", now=now)
    quota.reset_cache()  # süreç yeniden başladı: sayım dosyadan gelir
    assert not quota.consume("alphavantage", now=now)
    st["t"] += timedelta(minutes=2)  # UTC gün dönümü
    assert quota.consume("alphavantage", now=now)


def test_defaults_stay_under_free_plans():
    assert quota.limits("coingecko")["per_day"] * 31 <= 10_000
    assert quota.limits("alphavantage")["per_day"] < 25
    assert quota.limits("twelvedata")["per_day"] < 800 and quota.limits("twelvedata")["per_minute"] < 8
    assert quota.limits("tavily")["per_day"] * 31 <= 1000
