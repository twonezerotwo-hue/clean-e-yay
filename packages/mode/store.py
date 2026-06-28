"""Agent Mode override store — file-backed owner override'ları (spec §5/§40).

`packages/mode/config.py:load_config()` önce thresholds defaults'unu okur, sonra
bu store'daki owner override'larını ÜSTÜNE uygular. Store boşsa davranış = saf
config (bozulmama garantisi — ana thresholds dosyası ASLA yazılmaz). Desen
`tf_target_store` / `rebalance_store` ile aynı: JSON dosyası, env path override,
thread-safe, bozuk dosya → boş.

PAPER_SAFE: store yalnızca Agent Mode filtresinin (mode/filter.py) okuduğu
profil/strateji izinlerini taşır. Bu filtre şu an conflict_resolver/shadow
gözleminde okunur; live decide_matrix auto-open'ı DEĞİŞTİRMEZ (Faz 4'e kadar).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT
from packages.mode.config import TRADE_PROFILES

_LOCK = threading.Lock()

# Yalnızca bu anahtarlar override edilebilir (whitelist — bilinmeyen anahtar
# reddedilir, ana config şeması korunur).
_BOOL_KEYS = (
    "allow_counter_context_trades",
    "allow_reversal_trades",
    "allow_trend_follow_trades",
    "allow_range_trades",
    "allow_breakout_trades",
    "watch_disabled_profiles",
    "close_disabled_profile_positions",
    "close_requires_riskgate_pass",
)
_PROFILE_LIST_KEYS = ("enabled_trade_profiles", "disabled_trade_profiles")


def _store_path() -> Path:
    p = Path(os.environ.get("AGENT_MODE_STORE_PATH", "data/runtime/agent_mode.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def load_overrides() -> dict:
    """Owner override dict'i (yalnızca set edilmiş anahtarlar). Bozuk/eksik → {}."""
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return data if isinstance(data, dict) else {}


def sanitize(payload: dict) -> dict:
    """Gelen payload'u güvenli override'a indir: yalnızca bilinen anahtarlar;
    profil listeleri geçerli profil adlarına kısıtlı; focus_mode str|None."""
    out: dict = {}
    if not isinstance(payload, dict):
        return out
    for k in _BOOL_KEYS:
        if k in payload:
            out[k] = bool(payload[k])
    for k in _PROFILE_LIST_KEYS:
        v = payload.get(k)
        if isinstance(v, list):
            # Sıra korunur, tekrarsız, yalnızca geçerli profiller.
            out[k] = [p for p in TRADE_PROFILES if p in v]
    if "focus_mode" in payload:
        fm = payload["focus_mode"]
        out["focus_mode"] = fm if (fm in TRADE_PROFILES) else None
    return out


def save_overrides(payload: dict) -> dict:
    """Sanitize edilmiş override'ları atomik yaz; kayıtlı dict'i döner."""
    clean = sanitize(payload)
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return clean


def clear() -> None:
    """Tüm override'ları sil → saf config'e dön (bozulmama testi için de kullanılır)."""
    path = _store_path()
    with _LOCK:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = ["clear", "load_overrides", "sanitize", "save_overrides"]
