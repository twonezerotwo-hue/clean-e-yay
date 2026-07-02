"""F5-4 — makine üretimi weights yaml'ları data/runtime/weights/ altına gider.

- Default çıkış dizini artık config/ değil data/runtime/weights/ (gitignore'lu);
  `WEIGHTS_OUTPUT_DIR` env override'ı aynen çalışır.
- Loader çift-yol okur: manifest'teki yol yoksa aynı dosya adı önce
  data/runtime/weights/, sonra config/ altında aranır (eski manifest'ler
  config/'e işaret eder — kırılmaz).
- Hiçbir yerde bulunamazsa baseline weights_v1.0.yaml'a düşer (bugünkü davranış).
"""
from __future__ import annotations

import json

import yaml

from packages.data.registry import loader as ld
from packages.learning import rebalance_store as rs


def _write_manifest(path, yaml_path: str) -> None:
    path.write_text(
        json.dumps({"version": "9.9.9", "yaml_path": yaml_path}), encoding="utf-8"
    )


def _write_weights(path, version: str = "9.9.9") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": version}), encoding="utf-8")


def test_default_output_dir_is_runtime(monkeypatch):
    monkeypatch.delenv("WEIGHTS_OUTPUT_DIR", raising=False)
    assert rs._weights_output_dir() == ld.WEIGHTS_RUNTIME_DIR
    assert rs._weights_output_dir() != ld.CONFIG_DIR


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("WEIGHTS_OUTPUT_DIR", str(tmp_path / "out"))
    assert rs._weights_output_dir() == tmp_path / "out"


def test_apply_payload_writes_to_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("WEIGHTS_OUTPUT_DIR", raising=False)
    runtime_dir = tmp_path / "runtime_weights"
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(ld, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(rs, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    rs._apply_payload({"version": "2.0.0"}, "2.0.0", "auto", None)

    written = runtime_dir / "weights_v2.0.0.yaml"
    assert written.exists()
    assert ld.load_active_weights() == {"version": "2.0.0"}


def test_loader_falls_back_to_runtime_dir(monkeypatch, tmp_path):
    """Eski manifest config/'e işaret eder ama dosya taşınmış → runtime'da bulunur."""
    runtime_dir = tmp_path / "runtime_weights"
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(ld, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    _write_weights(runtime_dir / "weights_v9.9.9.yaml")
    _write_manifest(manifest, str(tmp_path / "yok" / "weights_v9.9.9.yaml"))

    assert ld.load_active_weights() == {"version": "9.9.9"}


def test_loader_falls_back_to_config_dir(monkeypatch, tmp_path):
    """Yeni manifest runtime'a işaret eder ama dosya config'te → config'te bulunur."""
    runtime_dir = tmp_path / "runtime_weights"  # boş bırakılıyor
    config_dir = tmp_path / "config"
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(ld, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(ld, "CONFIG_DIR", config_dir)
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    _write_weights(config_dir / "weights_v9.9.9.yaml")
    _write_manifest(manifest, str(tmp_path / "yok" / "weights_v9.9.9.yaml"))

    assert ld.load_active_weights() == {"version": "9.9.9"}


def test_loader_fallback_handles_backslash_paths(monkeypatch, tmp_path):
    """Windows'ta yazılmış manifest (config\\weights_vX.yaml) POSIX'te de çözülür."""
    runtime_dir = tmp_path / "runtime_weights"
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(ld, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    _write_weights(runtime_dir / "weights_v9.9.9.yaml")
    _write_manifest(manifest, "eski_dizin\\weights_v9.9.9.yaml")

    assert ld.load_active_weights() == {"version": "9.9.9"}


def test_missing_everywhere_falls_back_to_baseline(monkeypatch, tmp_path):
    """Manifest kırık + dosya hiçbir yerde yok → baseline weights_v1.0.yaml."""
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(ld, "WEIGHTS_RUNTIME_DIR", tmp_path / "bos")
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    _write_manifest(manifest, str(tmp_path / "yok" / "weights_v0.0.1.yaml"))

    assert ld._active_weights_yaml() == ld.CONFIG_DIR / ld.DEFAULT_WEIGHTS_FILE


def test_manifest_yaml_path_points_to_runtime_after_apply(monkeypatch, tmp_path):
    """Yazılan manifest'in yaml_path'i runtime dizinini gösterir (repo-dışı tmp →
    absolute string; loader bunu da çözer)."""
    monkeypatch.delenv("WEIGHTS_OUTPUT_DIR", raising=False)
    runtime_dir = tmp_path / "runtime_weights"
    manifest = tmp_path / "weights_active.json"
    monkeypatch.setattr(rs, "WEIGHTS_RUNTIME_DIR", runtime_dir)
    monkeypatch.setenv("WEIGHTS_MANIFEST_PATH", str(manifest))

    yaml_path_str = rs._apply_payload({"version": "3.0.0"}, "3.0.0", "auto", None)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["yaml_path"] == yaml_path_str
    assert "runtime_weights" in yaml_path_str
