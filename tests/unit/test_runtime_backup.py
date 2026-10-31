"""Kritik durum yedeği: yalnız okur, doğrular, saklama süresini uygular."""
from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packages.ops import backup

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "weights").mkdir()
    (root / "decision_log.jsonl").write_bytes(b'{"a": 1}\n{"a": 2}\n{"a": 3')  # yarım son satır
    (root / "paper_audit.jsonl").write_bytes(b'{"event": "OPENED"}\n')
    (root / "regime_state.json").write_text('{"regime": "RISK_ON"}', encoding="utf-8")
    (root / "weights" / "weights_v1.0.0.yaml").write_text("w: 1\n", encoding="utf-8")
    for env, name in (
        ("PAPER_STATE_PATH", "paper_state.json"),
        ("DECISION_LOG_PATH", "decision_log.jsonl"),
        ("PAPER_AUDIT_PATH", "paper_audit.jsonl"),
        ("COMPLIANCE_LOG_PATH", "compliance_log.jsonl"),
        ("RISK_HALT_PATH", "risk_halts.json"),
        ("WEIGHTS_MANIFEST_PATH", "weights_active.json"),
        ("AGENT_MODE_STORE_PATH", "agent_mode.json"),
        ("GOVERNOR_PROPOSALS_PATH", "governor_proposals.json"),
        ("REGIME_STATE_PATH", "regime_state.json"),
        ("TICKETS_PATH", "tickets.json"),
        ("PAPER_CANARY_PATH", "paper_canary.json"),
        ("WEIGHTS_OUTPUT_DIR", "weights"),
    ):
        monkeypatch.setenv(env, str(root / name))
    monkeypatch.setenv("DECISION_RECORD_DIR", str(root / "decision_record"))  # diğer testlerin kaydı sızmasın
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("BACKUP_STATUS_PATH", str(tmp_path / "backup_status.json"))
    monkeypatch.delenv("BACKUP_RETENTION_DAYS", raising=False)
    return root


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_backup_reads_only_and_restore_check_passes(runtime):
    before = _snapshot(runtime)
    result = backup.run(NOW)
    assert _snapshot(runtime) == before  # kaynak dosyalar değişmedi
    assert result["status"] == "OK"
    assert result["restore_check"]["status"] == "OK"
    names = {f["name"] for f in result["files"]}
    assert names == {"decision_log.jsonl", "paper_audit.jsonl", "regime_state.json", "weights/weights_v1.0.0.yaml"}
    assert "paper_state.json" in result["missing"]
    with zipfile.ZipFile(result["archive"]) as zf:
        assert zf.read("decision_log.jsonl") == b'{"a": 1}\n{"a": 2}\n'  # yarım satır alınmadı
    assert backup.read_status()["last_ok_at"] == NOW.isoformat()


def test_valid_paper_state_passes_real_loader(runtime):
    from packages.paper.state import PaperState

    state = PaperState(equity_usd=25_000.0, peak_equity_usd=25_000.0)
    (runtime / "paper_state.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")
    result = backup.run(NOW)
    assert result["status"] == "OK"
    assert "paper_state.json" in {f["name"] for f in result["files"]}


@pytest.mark.parametrize("payload", ['{"positions": "bozuk"}', '{"equity_usd": 1, "open_positions": ["bozuk"]}'])
def test_broken_paper_state_is_flagged(runtime, payload):
    (runtime / "paper_state.json").write_text(payload, encoding="utf-8")
    result = backup.run(NOW)
    assert result["status"] == "FAILED"
    assert any(item.startswith("paper_state.json") for item in result["unreadable"])


def test_corrupt_json_is_reported_not_raised(runtime):
    (runtime / "regime_state.json").write_text("{bozuk", encoding="utf-8")
    result = backup.run(NOW)
    assert result["status"] == "FAILED"
    assert result["last_ok_at"] is None
    assert result["restore_check"]["errors"]


def test_run_if_due_skips_recent_backup(runtime):
    assert backup.run_if_due(NOW)["ran"] is True
    assert backup.run_if_due(NOW + timedelta(hours=2))["ran"] is False
    assert backup.run_if_due(NOW + timedelta(hours=21))["ran"] is True


def test_retention_prunes_only_own_old_archives(runtime, tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    old = folder / "eyay-runtime-20261001T000000Z.zip"
    old.write_bytes(b"x")
    recent = folder / "eyay-runtime-20261029T000000Z.zip"
    recent.write_bytes(b"x")
    other = folder / "baska-dosya.zip"
    other.write_bytes(b"x")
    result = backup.run(NOW)
    assert result["pruned"] == [old.name]
    assert not old.exists() and recent.exists() and other.exists()


def test_restore_writes_only_to_target(runtime, tmp_path):
    archive = Path(backup.run(NOW)["archive"])
    target = tmp_path / "geri"
    written = backup.restore(archive, target)
    assert {p.relative_to(target).as_posix() for p in written} >= {"regime_state.json", "weights/weights_v1.0.0.yaml"}
    assert json.loads((target / "regime_state.json").read_text(encoding="utf-8")) == {"regime": "RISK_ON"}
