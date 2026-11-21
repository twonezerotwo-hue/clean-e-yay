"""Source ve feature registry yükleyicisi."""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
# F5-4 — makine üretimi weights yaml'larının dizini (gitignore'lu). config/ = insan
# elinden çıkan dosyalar, data/runtime/weights/ = trainer/auto-apply üretimi.
WEIGHTS_RUNTIME_DIR = REPO_ROOT / "data" / "runtime" / "weights"

DEFAULT_WEIGHTS_FILE = "weights_v1.0.yaml"


# K5 (owner, 2026-10-02) — ağırlıkların TEK kaynağı git: config/weights_active.json.
# Varsa runtime manifest'in (data/runtime/weights_active.json) önüne geçer → lokal
# ve AWS aynı ağırlıkla çalışır. Yoksa (eski kurulum) runtime manifest'e düşülür.
GIT_WEIGHTS_MANIFEST = CONFIG_DIR / "weights_active.json"


def weights_manifest_path() -> Path:
    """Aktif weights manifest yolu — env her çağrıda okunur (testler için).

    Öncelik: WEIGHTS_MANIFEST_PATH env > config/weights_active.json (git) >
    data/runtime/weights_active.json (eski, ortam-başına)."""
    env = os.environ.get("WEIGHTS_MANIFEST_PATH")
    if env:
        p = Path(env)
        return p if p.is_absolute() else REPO_ROOT / p
    if GIT_WEIGHTS_MANIFEST.exists():
        return GIT_WEIGHTS_MANIFEST
    return REPO_ROOT / "data" / "runtime" / "weights_active.json"


@lru_cache(maxsize=1)
def load_source_registry() -> dict:
    path = CONFIG_DIR / "source_registry_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_feature_registry() -> dict:
    path = CONFIG_DIR / "feature_registry_v1.0.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# Süreçte yüklenen eşik dosyasının özeti (diskteki dosya sonradan değişse de).
_LOADED: dict = {"thresholds_sha": None}


@lru_cache(maxsize=1)
def _load_thresholds_base() -> dict:
    """Disk'ten okunan ham thresholds config (cache'li, tek kaynak). Okunan baytların
    özeti yükleme anında tutulur: karar damgası yüklenen ayarı göstersin."""
    raw = (CONFIG_DIR / "thresholds_v1.0.yaml").read_bytes()
    _LOADED["thresholds_sha"] = hashlib.sha256(raw).hexdigest()[:12]
    return yaml.safe_load(raw.decode("utf-8"))


def thresholds_sha() -> str:
    """Bu süreçte YÜKLENMİŞ eşik dosyasının özeti (12 hex)."""
    _load_thresholds_base()
    return _LOADED["thresholds_sha"]


# CP4 — config-injection seam. lru_cache'li base'in ÜSTÜNE in-process override
# enjekte eder (deep-merge). Backtest A/B parametre-taraması ve eşik önericisi bunu
# kullanır; @lru_cache artık A/B'yi engellemiyor. contextvar →
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
    """Etkin thresholds config = cache'li base + (varsa) contextvar override'ı
    (backtest A/B, threshold_override). Canlı eşik YALNIZ owner'ın config dosyasından
    gelir: dosya tabanlı otomatik eşik ayarı 21 Kasım 2026'da owner kararıyla
    kaldırıldı. Override yoksa base BİREBİR döner (zero-copy) — sıcak yol (decision
    engine ~11 çağrı) ek yük almaz."""
    base = _load_thresholds_base()
    ctx_ov = _thresholds_override.get()
    return _deep_merge(base, ctx_ov) if ctx_ov else base


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


def _find_weights_by_name(yaml_path: str) -> Path | None:
    """F5-4 çift-yol arama: manifest'teki yol yoksa aynı dosya adını önce
    data/runtime/weights/ (makine), sonra config/ (insan) altında dene. Eski
    manifest'ler config/'e işaret eder; dosya taşınmışsa da bulunur."""
    name = Path(yaml_path.replace("\\", "/")).name
    if not name:
        return None
    for base in (WEIGHTS_RUNTIME_DIR, CONFIG_DIR):
        cand = base / name
        if cand.exists():
            return cand
    return None


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
                found = _find_weights_by_name(str(yaml_path))
                if found is not None:
                    return found
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


def _file_sha(path: Path) -> str | None:
    """Dosyanın SHA-256'sı (ilk 12 hex — kısa ama çakışmasız yeter). Yok → None."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def config_provenance() -> dict:
    """Karar anındaki config köken damgası (denetim: "canlı ağırlıklar hangi
    dosyadan? git commit'inden yeniden-üretilemiyor"). Aktif weights sürümü +
    weights YAML + thresholds YAML + manifest SHA-256'ları. Karar log'una
    açılış anında basılır → her kayıt hangi config'le üretildiğini taşır.
    Salt-okur; hata → alanlar None (uydurma yok)."""
    return {
        "weights_version": active_weights_version(),
        "weights_sha": _file_sha(_active_weights_yaml()),
        "thresholds_sha": thresholds_sha(),
        "manifest_sha": _file_sha(weights_manifest_path()),
    }
