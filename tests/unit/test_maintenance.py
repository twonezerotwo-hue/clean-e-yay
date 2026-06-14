"""Phase 2e — owner-admin paper maintenance tests (archive / repair / reset).

Acceptance (paper-safe, non-destructive, NO_EXECUTION):
- archive writes a timestamped file and never mutates current state;
- repair dry-run reports planned changes but writes nothing;
- repair non-dry-run archives BEFORE applying + saving;
- reset archives before replacing state and preserves the decision log by default;
- every result carries paper_safe / no_execution;
- missing/corrupt state is handled safely (no crash, no write);
- maintenance opens/sizes/triggers no trade and makes no broker/network call —
  so there is no RiskGate decision to bypass.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from packages.paper import maintenance


@pytest.fixture
def mnt_env(tmp_path, monkeypatch):
    """Isolated paper state; archive dir defaults next to STATE_PATH (→ tmp)."""
    from packages.paper import state as ps

    monkeypatch.setattr(ps, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    return {"state": ps, "tmp": tmp_path}


def _save(ps, **over):
    st = ps._initial_state()
    for k, v in over.items():
        setattr(st, k, v)
    ps.save(st)
    return st


def _archives(tmp) -> list[Path]:
    return list((tmp / "paper_archives").glob("*.json"))


# ---------- 1 + 2. archive ----------

def test_archive_creates_file(mnt_env) -> None:
    _save(mnt_env["state"])
    res = maintenance.archive_state("manual-check")
    assert res.status == "ok"
    assert res.action == "archive" and res.dry_run is False
    assert res.archive_path is not None and Path(res.archive_path).exists()
    assert "manual-check" in Path(res.archive_path).name


def test_archive_does_not_mutate_state(mnt_env) -> None:
    ps = mnt_env["state"]
    _save(ps, equity_usd=12345.0, peak_equity_usd=20000.0)
    before = ps.STATE_PATH.read_text(encoding="utf-8")
    maintenance.archive_state("snapshot")
    assert ps.STATE_PATH.read_text(encoding="utf-8") == before


# ---------- 3 + 4. repair ----------

def test_repair_dry_run_reports_without_writing(mnt_env) -> None:
    ps = mnt_env["state"]
    _save(ps, equity_usd=11000.0, peak_equity_usd=9000.0)  # peak below equity
    before = ps.STATE_PATH.read_text(encoding="utf-8")
    res = maintenance.repair_state(dry_run=True)
    assert res.dry_run is True and res.changed is True
    assert any("peak_equity_usd" in c for c in res.changes)
    assert res.archive_path is None
    # nothing written: state untouched, no archive created
    assert ps.STATE_PATH.read_text(encoding="utf-8") == before
    assert _archives(mnt_env["tmp"]) == []


def test_repair_non_dry_run_archives_then_applies(mnt_env) -> None:
    ps = mnt_env["state"]
    _save(ps, equity_usd=11000.0, peak_equity_usd=9000.0)
    res = maintenance.repair_state(dry_run=False)
    assert res.status == "ok" and res.changed is True
    assert res.archive_path is not None and Path(res.archive_path).exists()
    # archive holds the PRE-repair value; live state is fixed.
    archived = json.loads(Path(res.archive_path).read_text(encoding="utf-8"))
    assert archived["peak_equity_usd"] == 9000.0
    assert ps.load().peak_equity_usd == 11000.0


def test_repair_neutralizes_negative_size(mnt_env) -> None:
    ps = mnt_env["state"]
    st = ps._initial_state()
    st.open_positions.append(ps.Position(
        id="p1", symbol="BTCUSD", side="long", entry_price=100.0,
        current_price=100.0, size_usd=-500.0, sl=96.0, tp=108.0, opened_at="t",
    ))
    ps.save(st)
    res = maintenance.repair_state(dry_run=False)
    assert any("size_usd" in c for c in res.changes)
    assert ps.load().open_positions[0].size_usd == 0.0  # neutralized, not closed
    assert len(ps.load().open_positions) == 1            # position NOT removed


# ---------- 5 + 6. reset ----------

def test_reset_archives_then_resets(mnt_env) -> None:
    ps = mnt_env["state"]
    _save(ps, equity_usd=42000.0, peak_equity_usd=50000.0, realized_pnl_usd=1234.0)
    res = maintenance.reset_state("owner-fresh-start")
    assert res.status == "ok" and res.changed is True
    archived = json.loads(Path(res.archive_path).read_text(encoding="utf-8"))
    assert archived["equity_usd"] == 42000.0  # old state preserved in archive
    fresh = ps.load()
    assert fresh.equity_usd == ps._initial_state().equity_usd
    assert fresh.realized_pnl_usd == 0.0 and fresh.open_positions == []


def test_reset_preserves_decision_log_by_default(mnt_env, monkeypatch) -> None:
    from packages.learning import decision_log
    from packages.paper.state import Trade

    log_path = mnt_env["tmp"] / "decision_log.jsonl"
    monkeypatch.setenv("DECISION_LOG_PATH", str(log_path))
    decision_log.record_close(Trade(
        id="t1", symbol="BTCUSD", side="long", entry_price=100.0, exit_price=110.0,
        pnl_usd=10.0, opened_at="o", closed_at="c", close_reason="TP_HIT",
    ))
    assert log_path.exists()

    _save(mnt_env["state"])
    res = maintenance.reset_state("reset", preserve_learning=True)
    # decision log untouched by the paper-state reset
    assert log_path.exists() and len(decision_log.read_recent()) == 1
    assert any("preserved" in w for w in res.warnings)


# ---------- 7 + 8. safety flags ----------

def test_results_carry_paper_safe_and_no_execution(mnt_env) -> None:
    _save(mnt_env["state"])
    results = [
        maintenance.archive_state("a"),
        maintenance.repair_state(dry_run=True),
        maintenance.reset_state("r"),
    ]
    for res in results:
        assert res.paper_safe is True and res.no_execution is True
        d = res.to_dict()
        assert d["paper_safe"] is True and d["no_execution"] is True


# ---------- 9. missing / corrupt state ----------

def test_repair_handles_missing_state(mnt_env) -> None:
    res = maintenance.repair_state(dry_run=True)  # no state file at all
    assert res.status == "no_op" and res.changed is False
    assert "no_state_file" in res.warnings


def test_repair_handles_corrupt_state_without_rewrite(mnt_env) -> None:
    ps = mnt_env["state"]
    ps.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ps.STATE_PATH.write_text("{ not valid json", encoding="utf-8")
    res = maintenance.repair_state(dry_run=False)  # must not crash or rewrite
    assert res.status == "no_op" and res.changed is False
    assert any("unreadable_state" in w for w in res.warnings)
    assert ps.STATE_PATH.read_text(encoding="utf-8") == "{ not valid json"


# ---------- 10 + 11. no execution / no RiskGate bypass ----------

def test_maintenance_has_no_broker_or_network_calls() -> None:
    src = inspect.getsource(maintenance)
    forbidden = (
        "import requests", "import httpx", "import socket", "urllib",
        "open_position(", "attempt_open(", "close_position(",
        "place_order", "evaluate_risk(", "import lifecycle",
    )
    for token in forbidden:
        assert token not in src, f"maintenance must not reference {token}"


def test_maintenance_opens_no_trades(mnt_env) -> None:
    ps = mnt_env["state"]
    _save(ps, equity_usd=11000.0, peak_equity_usd=9000.0)
    maintenance.archive_state("a")
    maintenance.repair_state(dry_run=False)
    maintenance.reset_state("r")
    # No maintenance path ever opened a position → no RiskGate decision to bypass.
    assert ps.load().open_positions == []


# ---------- 12. thin HTTP endpoints return structured results ----------

@pytest.fixture
def api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from packages.paper import state as ps

    monkeypatch.setattr(ps, "STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setenv("PAPER_ARCHIVE_DIR", str(tmp_path / "arch"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    ps.save(ps._initial_state())
    return TestClient(app)


def test_api_archive_returns_structured_result(api_client) -> None:
    r = api_client.post(
        "/api/v1/paper-trading/maintenance/archive", params={"reason": "owner-check"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "archive" and body["status"] == "ok"
    assert body["paper_safe"] is True and body["no_execution"] is True
    assert body["archive_path"]


def test_api_repair_defaults_to_dry_run(api_client) -> None:
    r = api_client.post("/api/v1/paper-trading/maintenance/repair")
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "repair" and body["dry_run"] is True
    assert body["no_execution"] is True


def test_api_reset_archives_and_resets(api_client) -> None:
    r = api_client.post(
        "/api/v1/paper-trading/maintenance/reset", params={"reason": "fresh-start"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "reset" and body["changed"] is True
    assert body["paper_safe"] is True and body["archive_path"]
