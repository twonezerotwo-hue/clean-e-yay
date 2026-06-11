"""Source ve feature registry yükleyicisi."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"


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
