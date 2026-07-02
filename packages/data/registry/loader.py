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


def _runtime_threshold_override() -> dict:
    """CP4 otonom eşik-ayarı — file-backed runtime override (yalnız `THRESHOLD_AUTOTUNE`
    açıkken). Kapalıyken `{}` (dosya bile okunmaz → bayt-aynı). Local import: loader
    düşük seviyeli, threshold_overrides ondan REPO_ROOT alır (döngü önlenir)."""
    try:
        from packages.data.registry import threshold_overrides
        return threshold_overrides.active_tree()
    except Exception:  # store yok/bozuk → base (bozulma yok)
        return {}


def load_thresholds() -> dict:
    """Etkin thresholds config = cache'li base + (varsa) override'lar (deep-merge).

    İki override kaynağı: (1) file-backed runtime override (CP4 otonom eşik-ayarı,
    yalnız flag açıkken), (2) contextvar (backtest A/B, threshold_override). Hiçbiri
    yoksa base BİREBİR döner (zero-copy, bayt-aynı) — sıcak yol (decision engine ~11
    çağrı) ek yük almaz."""
    base = _load_thresholds_base()
    merged = base
    runtime_ov = _runtime_threshold_override()
    if runtime_ov:
        merged = _deep_merge(merged, runtime_ov)
    ctx_ov = _thresholds_override.get()
    if ctx_ov:
        merged = _deep_merge(merged, ctx_ov)
    return base if merged is base else merged


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
