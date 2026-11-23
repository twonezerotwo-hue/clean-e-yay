"""Ücretsiz sağlayıcı kotası: günlük ve dakikalık sınır, gün dönümü, kalıcılık."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import quota


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "quota.json"))


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
    assert not quota.consume("alphavantage", now=now)
    st["t"] += timedelta(minutes=2)  # UTC gün dönümü
    assert quota.consume("alphavantage", now=now)


def test_defaults_stay_under_free_plans():
    assert quota.limits("coingecko")["per_day"] * 31 <= 10_000
    assert quota.limits("alphavantage")["per_day"] < 25
    assert quota.limits("twelvedata")["per_day"] < 800 and quota.limits("twelvedata")["per_minute"] < 8
    assert quota.limits("tavily")["per_day"] * 31 <= 1000


_CHILD = """
import sys
sys.path.insert(0, sys.argv[1])
from packages.data.providers import quota
for _ in range(int(sys.argv[2])):
    quota.consume("race_test")
"""


def test_separate_processes_do_not_lose_counts(tmp_path, monkeypatch):
    """API, tick ve öğrenme ayrı süreç: üç süreç × 25 çağrı dosyada 75 olmalı
    (eski kodda her süreç kendi bellek kopyasını yazıyordu → 25)."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / "race.json"
    env = dict(os.environ, PROVIDER_QUOTA_PATH=str(path),
               PROVIDER_QUOTA_RACE_TEST_PER_DAY="0", PROVIDER_QUOTA_RACE_TEST_PER_MINUTE="0")
    root = str(Path(__file__).resolve().parents[2])
    procs = [subprocess.Popen([sys.executable, "-c", _CHILD, root, "25"], env=env) for _ in range(3)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    assert json.loads(path.read_text(encoding="utf-8"))["race_test"]["count"] == 75
