"""Stres testi (VaR/CVaR, en kötü gün, limit kıyası) ve sürüm kaydı."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.types import OHLCVBar
from packages.ops import registry
from packages.risk import stress

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(symbol, closes):
    return [OHLCVBar(symbol=symbol, timeframe="1d", ts=T0 + timedelta(days=i), open=c, high=c,
                     low=c, close=c, volume=1.0) for i, c in enumerate(closes)]


@pytest.fixture
def prices(monkeypatch):
    from packages.data.providers.ohlcv import cache
    # 100 gün: her 10. günde −%5, diğer günler +%0,5.
    closes, c = [], 100.0
    for i in range(101):
        closes.append(c)
        c *= 0.95 if i % 10 == 9 else 1.005
    series = {"BTCUSD": _bars("BTCUSD", closes)}
    monkeypatch.setattr(cache, "load", lambda s, tf: SimpleNamespace(bars=series[s]) if s in series else None)


def _state(*positions, equity=100_000.0):
    return SimpleNamespace(equity_usd=equity, open_positions=list(positions))


def test_long_book_tail_risk_and_limit_check(prices):
    pos = SimpleNamespace(symbol="BTCUSD", side="long", size_usd=50_000.0)
    out = stress.report(_state(pos))
    assert out["status"] == "OK" and out["days"] == 100 and out["priced"] == 1
    # en kötü gün: 50k × −%5 = −2.500$ → %2,5 sermaye
    assert out["worst_day_pct"] == pytest.approx(2.5, abs=1e-3)
    assert out["var_95_pct"] == pytest.approx(2.5, abs=1e-3) and out["cvar_99_pct"] == pytest.approx(2.5, abs=1e-3)
    assert out["exceeds_daily_limit"] is True       # %2,5 > %2 günlük sınır
    short = SimpleNamespace(symbol="BTCUSD", side="short", size_usd=50_000.0)
    assert stress.report(_state(short))["worst_day_pct"] == pytest.approx(0.25, abs=1e-3)


def test_unpriced_and_empty_book(prices):
    pos = SimpleNamespace(symbol="XLP", side="long", size_usd=10_000.0)
    out = stress.report(_state(pos))
    assert out["status"] == "NO_DATA" and out["unpriced"] == ["XLP"]
    assert stress.report(_state())["status"] == "NO_EXPOSURE"


def test_registry_lists_versions():
    snap = registry.snapshot()
    assert {"code", "config", "weights", "models", "prompts", "learning_engines"} <= set(snap)
    assert snap["prompts"]["chat"] and snap["models"]["ollama"]
    assert snap["learning_engines"]["subsignal_scorecard"].startswith("subsignal_scorecard")
    assert set(snap["history"]) == {"weights", "tf_targets", "guards", "flags"}


def test_tick_stage_metrics_from_heartbeat(tmp_path, monkeypatch):
    from packages.ops import heartbeat, metrics
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", str(tmp_path / "hb.json"))
    for total in (10.0, 20.0, 30.0):
        heartbeat.record("tick_worker", status="OK", run_id="r", started_at="s", completed_at="c",
                         stages={"snapshot": total - 2, "decide": 1.0, "total": total})
    out = metrics.tick_metrics()
    assert out["samples"] == 3 and out["status"] == "OK"
    assert out["stages_sec"]["total"] == {"last": 30.0, "p50": 20.0, "p95": 30.0, "max": 30.0}
    assert out["stages_sec"]["decide"]["p50"] == 1.0
