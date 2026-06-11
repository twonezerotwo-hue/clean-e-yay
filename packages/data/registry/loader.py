"""Source ve feature registry yükleyicisi."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"

DEFAULT_WEIGHTS_FILE = "weights_v1.0.yaml"


def weights_manifest_path() -> Path:
    """Aktif weights manifest yolu — env her çağrıda okunur (testler için)."""
    p = Path(
        os.environ.get("WEIGHTS_MANIFEST_PATH", "data/runtime/weights_active.json")
    )
    return p if p.is_absolute() else REPO_ROOT / p


@lru_cache(maxsize=1)
def load_source_registry() -> dict:
    path = CONFIG_DIR / "source_registry_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_feature_registry() -> dict:
    path = CONFIG_DIR / "feature_registry_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_weights() -> dict:
    path = CONFIG_DIR / "weights_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_thresholds() -> dict:
    path = CONFIG_DIR / "thresholds_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve_path(p: str) -> Path:
    pth = Path(p)
    return pth if pth.is_absolute() else REPO_ROOT / pth


def _active_weights_yaml() -> Path:
    """Aktif weights yaml dosyasının yolu (approve sonrası güncellenir)."""
    manifest = weights_manifest_path()
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            yaml_path = data.get("yaml_path")
            if yaml_path:
                p = _resolve_path(yaml_path)
                if p.exists():
                    return p
        except (OSError, json.JSONDecodeError):
            pass
    return CONFIG_DIR / DEFAULT_WEIGHTS_FILE


def load_active_weights() -> dict:
    """Aktif ağırlıkları okur (manifest > baseline). Cache'siz — approve
    sonrası anında yansır."""
    path = _active_weights_yaml()
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def active_weights_version() -> str:
    cfg = load_active_weights()
    return str(cfg.get("version", "unknown"))
