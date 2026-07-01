"""Source ve feature registry yükleyicisi."""
from __future__ import annotations

import contextvars
import json
import os
from contextlib import contextmanager
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
def _load_thresholds_base() -> dict:
    """Disk'ten okunan ham thresholds config (cache'li, tek kaynak)."""
    path = CONFIG_DIR / "thresholds_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# CP4 — config-injection seam. lru_cache'li base'in ÜSTÜNE in-process override
# enjekte eder (deep-merge). Backtest A/B parametre-taraması + (ileride) otonom
# eşik-ayarı bunu kullanır; @lru_cache artık A/B'yi engellemiyor. contextvar →
# thread/async-güvenli, scope dışında otomatik temizlenir. Override yokken
# load_thresholds base'i BİREBİR (zero-copy) döner → sıcak yol bayt-aynı.
_thresholds_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "thresholds_override", default=None
)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_thresholds() -> dict:
    """Etkin thresholds config = cache'li base + (varsa) aktif override (deep-merge).

    Override yoksa base BİREBİR döner (zero-copy, bayt-aynı) — sıcak yol (decision
    engine ~11 çağrı) ek yük almaz."""
    base = _load_thresholds_base()
    override = _thresholds_override.get()
    if not override:
        return base
    return _deep_merge(base, override)


@contextmanager
def threshold_override(overrides: dict | None):
    """CP4 seam — `overrides`'i load_thresholds'a enjekte et (deep-merge), scope
    bitince temizle. Boş/None → no-op (base). A/B backtest: `with threshold_override(
    {"consensus": {"min_confidence": 0.6}}): run_signal_backtest(...)`."""
    token = _thresholds_override.set(overrides or None)
    try:
        yield
    finally:
        _thresholds_override.reset(token)


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
