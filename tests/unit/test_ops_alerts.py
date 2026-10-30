"""Operasyon alarmları: kural, tekrar engeli, düzeldi bildirimi; karar etkisi yok."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.ops import alerts

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from packages import notifications
    from packages.data import snapshot_store
    from packages.data.providers import quota
    from packages.ops import system_health

    monkeypatch.setenv("OPS_ALERTS_STATE_PATH", str(tmp_path / "ops_alerts_state.json"))
    monkeypatch.setenv("BACKUP_STATUS_PATH", str(tmp_path / "backup_status.json"))
    monkeypatch.setenv("PROVIDER_QUOTA_PATH", str(tmp_path / "provider_quota.json"))
    monkeypatch.setattr(notifications, "NOTIFICATIONS_PATH", tmp_path / "notifications.jsonl")
    quota.reset_cache()
    world = {
        "tick": {"stale": False, "age_seconds": 5.0, "duration_ms": 20_000},
        "snapshot": {"provider_status": {"kraken": {"status": "ok"}, "mock": {"status": "degraded"}}, "dqs": {"fallback_used": False}},
    }
    monkeypatch.setattr(system_health, "_worker_view", lambda name, threshold, now: dict(world["tick"]))
    monkeypatch.setattr(snapshot_store, "latest", lambda: world["snapshot"])
    (tmp_path / "backup_status.json").write_text(json.dumps({"status": "OK", "last_ok_at": NOW.isoformat()}), encoding="utf-8")
    yield world
    quota.reset_cache()


def _sent():
    from packages import notifications

    return [n for n in notifications.list_recent(limit=50) if n.type == "ops_alert"]


def test_healthy_system_sends_nothing_and_mock_is_not_a_source(env):
    result = alerts.evaluate(NOW)
    assert result == {"active": [], "sent": 0}
    assert _sent() == []


def test_alert_once_then_repeat_then_resolved(env):
    env["tick"] = {"stale": True, "age_seconds": 400.0, "duration_ms": None}
    assert alerts.evaluate(NOW)["sent"] == 1
    assert alerts.evaluate(NOW + timedelta(minutes=10))["sent"] == 0  # tekrar engeli
    assert alerts.evaluate(NOW + timedelta(hours=6))["sent"] == 1     # hatırlatma
    env["tick"] = {"stale": False, "age_seconds": 3.0, "duration_ms": 20_000}
    assert alerts.evaluate(NOW + timedelta(hours=7))["sent"] == 1     # düzeldi
    titles = [n.title for n in _sent()]
    assert titles.count("Tick durdu") == 1 and "Tick durdu (sürüyor)" in titles and "Düzeldi: Tick durdu" in titles
    assert {n.priority for n in _sent() if n.title == "Tick durdu"} == {"critical"}


def test_slow_tick_and_degraded_provider(env):
    env["tick"] = {"stale": False, "age_seconds": 3.0, "duration_ms": 75_000}
    env["snapshot"]["provider_status"]["coingecko"] = {"status": "degraded"}
    env["snapshot"]["dqs"]["fallback_used"] = True  # karar yolu yedeğe düştü → ikincil kaynak da sayılır
    found = alerts.collect(NOW)
    assert set(found) == {"tick_slow", "provider_degraded"}
    assert "coingecko" in found["provider_degraded"]["title"] and "mock" not in found["provider_degraded"]["title"]


def test_quota_exhausted_today_only(env, tmp_path):
    (tmp_path / "provider_quota.json").write_text(json.dumps({
        "alphavantage": {"day": "2026-10-30", "count": 20},
        "twelvedata": {"day": "2026-10-29", "count": 700},
    }), encoding="utf-8")
    from packages.data.providers import quota

    quota.reset_cache()
    assert [k for k in alerts.collect(NOW) if k.startswith("quota:")] == ["quota:alphavantage"]


@pytest.mark.parametrize("status", [
    {"status": "FAILED", "last_ok_at": None, "restore_check": {"errors": ["paper_state.json: equity_usd yok"]}},
    {"status": "OK", "last_ok_at": (NOW - timedelta(hours=31)).isoformat()},
])
def test_backup_failure_or_too_old(env, tmp_path, status):
    (tmp_path / "backup_status.json").write_text(json.dumps(status), encoding="utf-8")
    assert "backup" in alerts.collect(NOW)


def test_no_backup_status_yet_is_not_an_alarm(env, tmp_path):
    (tmp_path / "backup_status.json").unlink()
    assert "backup" not in alerts.collect(NOW)
