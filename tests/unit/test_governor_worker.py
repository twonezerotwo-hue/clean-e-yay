"""Part 3 — Governor worker (observe-only, scheduler-driven) testleri.

Kapsam:
- run_once: generate→execute döngüsü, run metadata + run_store + heartbeat.
- DEĞİŞMEZ: worker attempt_open / paper / config'e dokunmaz (import bile etmez).
- Hata izolasyonu: generate patlasa bile worker COMPLETED_WITH_ERRORS döner.
- report worker_last_run'ı görür.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("GOVERNOR_TASKS_PATH", str(tmp_path / "governor_tasks.json"))
    monkeypatch.setenv("GOVERNOR_RUN_PATH", str(tmp_path / "governor_run.json"))
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", str(tmp_path / "heartbeats.json"))
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    return tmp_path


def test_run_once_returns_metadata(iso) -> None:
    from apps.governor_worker.main import run_once
    run = run_once()
    assert run["run_id"]
    assert run["status"] in {"COMPLETED", "COMPLETED_WITH_ERRORS", "NO_DATA"}
    assert "tasks_generated" in run
    assert "tasks_executed" in run


def test_run_once_persists_run_store(iso) -> None:
    from apps.governor_worker.main import run_once
    from packages.governor import run_store
    run = run_once()
    saved = run_store.load()
    assert saved is not None
    assert saved["run_id"] == run["run_id"]


def test_run_once_executes_generated_tasks(iso, monkeypatch) -> None:
    """generate() bir görev üretirse, worker onu koşar (auto_execute) ve
    history'e geçer."""
    from apps.governor_worker import main as worker
    from packages.governor import tasks

    # generate'i deterministik kıl: tek bir görev üret.
    monkeypatch.setattr(
        tasks, "generate", lambda: [tasks.enqueue("SYSTEM_HEALTH_REVIEW")]
    )
    run = worker.run_once()
    assert run["tasks_executed"] >= 1
    # kuyruk boşaldı, history doldu
    assert tasks.list_queue() == []
    assert len(tasks.load()["history"]) >= 1


def test_run_once_generate_failure_is_isolated(iso, monkeypatch) -> None:
    from apps.governor_worker import main as worker
    from packages.governor import tasks

    def _boom():
        raise RuntimeError("patladı")

    monkeypatch.setattr(tasks, "generate", _boom)
    run = worker.run_once()
    assert run["status"] == "COMPLETED_WITH_ERRORS"
    assert any("generate" in e for e in run["errors"])


def test_worker_does_not_import_paper_lifecycle() -> None:
    """DEĞİŞMEZ: governor worker kaynağında attempt_open / paper.lifecycle
    bağımlılığı OLMAMALI (paper açılışı yalnızca tick_worker'da)."""
    import inspect

    from apps.governor_worker import main as worker
    # Docstring "attempt_open çağrılmaz" diye AÇIKLAR — onu çıkar, gerçek kodu denetle.
    src = inspect.getsource(worker)
    code = src.replace(worker.__doc__ or "", "")
    assert "attempt_open" not in code
    assert "packages.paper" not in code
    assert "import" in code  # sanity


def test_report_sees_worker_last_run(iso) -> None:
    from apps.governor_worker.main import run_once
    from packages.governor import report

    run_once()
    r = report.build_report()
    assert r["worker_last_run"]["available"] is True
    assert r["worker_last_run"]["data"]["run_id"]
