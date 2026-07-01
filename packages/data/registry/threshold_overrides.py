"""CP4 (final) — otonom eşik-ayarı için runtime threshold override deposu.

`threshold_trainer` bir eşik nudge'ını (ör. `paper_trading.tp_rr_ratio`) backtest'le
doğrulayıp CANLIYA uygulamak istediğinde buraya yazar. `loader.load_thresholds`
bunu (yalnız `THRESHOLD_AUTOTUNE` flag açıkken) base config'in ÜSTÜNE deep-merge eder
— owner config dosyasına (thresholds_v1.0.yaml) DOKUNMADAN. `guard_overrides`'ın
(yön kill-switch) ve `weights_active.json` manifest'inin threshold ikizidir.

İki kanun:
* **Bayt-aynı (law 2):** `THRESHOLD_AUTOTUNE` OFF → `active_tree()` `{}` döner,
  load_thresholds hiç okumaz → sıcak yol birebir bugünkü. Flag ON + override yoksa
  yine `{}`.
* **Sıcak yolda sıfır ek yük (law 5):** okuma mtime-cache'li (guard_overrides deseni)
  — dosya değişmediyse tek `os.stat()` ile bellekten.

PAPER_SAFE / NO_EXECUTION: yalnız runtime durum dosyası; emir üretmez.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

_LOCK = threading.Lock()
_CACHE: dict = {"key": None, "data": {"overrides": {}}}
_OFF = {"0", "false", "no", "off", ""}


def autotune_enabled() -> bool:
    """`THRESHOLD_AUTOTUNE` flag (default OFF). Kapalıyken override okunmaz/uygulanmaz."""
    return os.environ.get("THRESHOLD_AUTOTUNE", "0").strip().lower() not in _OFF


def _path() -> Path:
    p = Path(os.environ.get("THRESHOLD_OVERRIDES_PATH", "data/runtime/threshold_overrides.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"overrides": {}}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("overrides"), dict):
        return _empty()
    return data


def _load_cached() -> dict:
    path = _path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        with _LOCK:
            _CACHE["key"] = None
            _CACHE["data"] = _empty()
            return _CACHE["data"]
    key = (str(path), mtime)
    with _LOCK:
        if _CACHE["key"] == key:
            return _CACHE["data"]
        data = _read(path)
        _CACHE["key"] = key
        _CACHE["data"] = data
        return data


def _write(data: dict) -> None:
    path = _path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
        _CACHE["key"] = None


def _nested(path: str, value) -> dict:
    """'a.b.c', v → {'a': {'b': {'c': v}}}."""
    keys = path.split(".")
    out: dict = {}
    cur = out
    for k in keys[:-1]:
        cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def active_tree() -> dict:
    """load_thresholds'ın merge edeceği nested override ağacı. Flag OFF → `{}`
    (byte-identical). Her aktif override path'i nested dict'e çevrilip birleştirilir."""
    if not autotune_enabled():
        return {}
    overrides = _load_cached().get("overrides", {})
    tree: dict = {}
    for path, entry in overrides.items():
        if isinstance(entry, dict) and "value" in entry:
            tree = _deep_merge(tree, _nested(path, entry["value"]))
    return tree


def get(path: str) -> dict | None:
    return _load_cached().get("overrides", {}).get(path)


def set_override(path: str, value, *, prev, by: str = "threshold_trainer") -> dict:
    """`path` eşiğini `value`'ya override et. `prev` = rollback için önceki değer."""
    data = _read(_path())
    entry = {
        "value": value,
        "prev": prev,
        "by": by,
        "at": datetime.now(UTC).isoformat(),
    }
    data.setdefault("overrides", {})[path] = entry
    _write(data)
    return entry


def revert(path: str) -> bool:
    """`path` override'ını kaldır (rollback / owner). Kaldırıldıysa True."""
    data = _read(_path())
    if path in data.get("overrides", {}):
        del data["overrides"][path]
        _write(data)
        return True
    return False


def active() -> dict[str, dict]:
    """Tüm aktif override'lar (panel/endpoint)."""
    return dict(_load_cached().get("overrides", {}))


__all__ = [
    "active",
    "active_tree",
    "autotune_enabled",
    "get",
    "revert",
    "set_override",
]
