from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.learning import forward_test


def _outcome(opened, pnl=10.0, r=1.0, reason="signal"):
    return SimpleNamespace(
        opened_at=opened.isoformat(),
        closed_at=(opened + timedelta(hours=1)).isoformat(),
        pnl=pnl,
        r_multiple=r,
        data_verified=True,
        open_reason=reason,
        exploration=False,
    )


def test_forward_test_starts_clock_and_is_running(tmp_path, monkeypatch):
    monkeypatch.setenv("FORWARD_TEST_90D_PATH", str(tmp_path / "forward.json"))
    now = datetime(2026, 10, 28, tzinfo=UTC)
    report = forward_test.run(now=now, outcomes=[_outcome(now, 5.0)])
    assert report["status"] == "RUNNING"
    assert report["remaining_days"] == 90.0
    assert report["promotion_ready"] is False
    assert report["paper_safe"] is True


def test_forward_test_preserves_start_and_excludes_manual(tmp_path, monkeypatch):
    path = tmp_path / "forward.json"
    monkeypatch.setenv("FORWARD_TEST_90D_PATH", str(path))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    forward_test.run(now=start, outcomes=[])
    report = forward_test.run(
        now=start + timedelta(days=90),
        outcomes=[
            _outcome(start + timedelta(days=10), 5.0),
            _outcome(start + timedelta(days=10), -2.0, -1.0, reason="owner_approved:manual"),
        ],
    )
    assert report["status"] == "COMPLETE"
    assert report["started_at"].startswith("2026-01-01")
    assert report["metrics"]["closed"] == 1
    assert report["promotion_ready"] is False


def test_forward_test_excludes_incomplete_provenance_from_clean_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("FORWARD_TEST_90D_PATH", str(tmp_path / "forward.json"))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    forward_test.run(now=start, outcomes=[])
    report = forward_test.run(
        now=start + timedelta(days=1),
        outcomes=[
            _outcome(start + timedelta(hours=1), 5.0),
            SimpleNamespace(
                opened_at=(start + timedelta(hours=2)).isoformat(),
                closed_at=(start + timedelta(hours=3)).isoformat(),
                pnl=100.0,
                r_multiple=4.0,
                data_verified=True,
                provenance_complete=False,
                open_reason="signal",
                exploration=False,
            ),
        ],
    )
    assert report["metrics"]["closed"] == 1
    assert report["excluded_incomplete"] == 1
