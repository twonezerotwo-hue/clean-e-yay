"""K5 — ağırlıkların tek kaynağı git (config/weights_active.json)."""
from __future__ import annotations

from packages.data.registry import loader


def test_git_manifest_wins_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("WEIGHTS_MANIFEST_PATH", raising=False)
    assert loader.weights_manifest_path() == loader.GIT_WEIGHTS_MANIFEST
    assert loader.active_weights_version() == "1.17.0"


def test_env_override_still_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(tmp_path / "m.json"))
    assert loader.weights_manifest_path() == tmp_path / "m.json"
    assert loader.active_weights_version() == "1.0.0"  # manifest yok → baseline


def test_owner_approval_writes_into_git_config(monkeypatch) -> None:
    monkeypatch.delenv("WEIGHTS_MANIFEST_PATH", raising=False)
    monkeypatch.delenv("WEIGHTS_OUTPUT_DIR", raising=False)
    from packages.learning import rebalance_store

    assert rebalance_store._weights_output_dir() == loader.CONFIG_DIR


def test_auto_rollback_is_retired_under_git_manifest(monkeypatch) -> None:
    monkeypatch.delenv("WEIGHTS_MANIFEST_PATH", raising=False)
    from packages.learning import weight_rollback

    assert weight_rollback.check_rollback() == {"status": "owner_gated"}
