"""CP3 — yön guard'ları için runtime kill-switch (override) deposu.

`guard_safety` kasası bir yön guard'ını canlıda izlerken expectancy baseline'ın
altına düşerse buraya bir **disable override** yazar. Engine seam'leri
(`engine._self_conflict_cfg`, `timeframe.load_config`) bu override'ı okuyup ilgili
guard'ı zorla KAPATIR — owner config dosyasına (thresholds_v1.0.yaml) DOKUNMADAN.

Bu, `weights_active.json` manifest pointer'ının (config'ten ayrı runtime override,
bkz. `loader.load_active_weights` — "cache'siz, anında yansır") guard ikizidir.

İki kanun gözetildi:
* **Bayt-aynı (law 2):** override YALNIZ bir guard'ı OFF'a zorlar; hiçbir zaman
  ON yapmaz. Override yokken seam'ler birebir bugünkü davranışı verir.
* **Sıcak yolda sıfır ek yük (law 5):** okuma mtime-cache'li — dosya değişmediyse
  tek `os.stat()` çağrısıyla bellekten döner (TA işine kıyasla ihmal edilebilir).

PAPER_SAFE / NO_EXECUTION: yalnız bir runtime durum dosyası; emir üretmez.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

_LOCK = threading.Lock()
# (path, mtime_ns) → parsed dict. Dosya değişmediyse yeniden okumayız.
_CACHE: dict = {"key": None, "data": {"overrides": {}}}


def _path() -> Path:
    p = Path(os.environ.get("GUARD_OVERRIDES_PATH", "data/runtime/guard_overrides.json"))
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
    """mtime-cache'li okuma. Dosya yoksa boş; değişmediyse bellekten döner."""
    path = _path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        # Dosya yok → boş (override aktif değil). Cache'i de boşla.
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
        # Yazımdan hemen sonra cache'i geçersiz kıl (aynı process anında görsün).
        _CACHE["key"] = None


def is_disabled(guard_key: str) -> bool:
    """`guard_key` için aktif bir kill-override var mı? Sıcak-yol güvenli (mtime-cache)."""
    entry = _load_cached().get("overrides", {}).get(guard_key)
    return bool(entry) and bool(entry.get("disabled"))


def set_disabled(guard_key: str, *, reason: str, by: str = "guard_safety") -> dict:
    """`guard_key`'i KAPALI'ya zorla (kasa rollback'i). Override kaydını döner."""
    data = _read(_path())  # tazeden oku (cache değil) — yarış önle
    entry = {
        "disabled": True,
        "reason": reason,
        "by": by,
        "at": datetime.now(UTC).isoformat(),
    }
    data.setdefault("overrides", {})[guard_key] = entry
    _write(data)
    return entry


def clear(guard_key: str) -> bool:
    """`guard_key` override'ını kaldır (owner yeniden canlıya almak isterse).
    Kaldırıldıysa True."""
    data = _read(_path())
    if guard_key in data.get("overrides", {}):
        del data["overrides"][guard_key]
        _write(data)
        return True
    return False


def active() -> dict[str, dict]:
    """Tüm aktif kill-override'lar (panel/endpoint için). Disabled olanlar."""
    return {
        k: v
        for k, v in _load_cached().get("overrides", {}).items()
        if isinstance(v, dict) and v.get("disabled")
    }


__all__ = ["active", "clear", "is_disabled", "set_disabled"]
