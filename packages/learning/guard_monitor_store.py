"""CP3 — yön guard'ları için izleme + rollback ledger'i (guard-agnostik).

`weight_autoapply_store`'un guard ikizidir: bir owner bir yön guard'ını canlıya
aldığında (config flag OFF→ON) burada bir izleme (MONITORING) açılır — enable
anındaki eşleştirilmiş baseline expectancy + örnek sayısı saklanır. learning_worker
yeterli yeni outcome birikince `guard_safety.check_guards()` ile post-enable
expectancy'i baseline ile kıyaslar; sonuç CONFIRMED ya da ROLLED_BACK olur.

Ağırlık rollback'inden farkı: aynı anda BİRDEN ÇOK guard bağımsız izlenebilir
(her guard_key kendi slot'unda). `last_seen`, geçiş tespiti için her guard'ın son
görülen HAM config-enabled durumunu tutar (override'dan bağımsız).

PAPER_SAFE / NO_EXECUTION: yalnız öğrenme-katmanı durum dosyası; emir üretmez.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT

_LOCK = threading.Lock()
_HISTORY_CAP = 100


def _store_path() -> Path:
    p = Path(os.environ.get("GUARD_MONITOR_STORE_PATH", "data/runtime/guard_monitor.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"monitors": {}, "last_seen": {}, "history": []}


def load() -> dict:
    path = _store_path()
    with _LOCK:
        if not path.exists():
            return _empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty()
    if not isinstance(data, dict):
        return _empty()
    if not isinstance(data.get("monitors"), dict):
        data["monitors"] = {}
    if not isinstance(data.get("last_seen"), dict):
        data["last_seen"] = {}
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


def _save(data: dict) -> None:
    path = _store_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)


def get_last_seen() -> dict[str, bool]:
    """Her guard'ın son görülen HAM config-enabled durumu (geçiş tespiti için)."""
    return {k: bool(v) for k, v in load().get("last_seen", {}).items()}


def set_last_seen(states: dict[str, bool]) -> None:
    """Güncel ham config-enabled snapshot'ını kaydet (sync sonunda çağrılır)."""
    data = load()
    data["last_seen"] = {k: bool(v) for k, v in states.items()}
    _save(data)


def get_active(guard_key: str) -> dict | None:
    """`guard_key` için izlenen (henüz çözülmemiş) enable varsa döner."""
    mon = load().get("monitors", {}).get(guard_key)
    return mon if isinstance(mon, dict) else None


def all_active() -> dict[str, dict]:
    """Tüm aktif izlemeler (panel/endpoint için)."""
    return {
        k: v
        for k, v in load().get("monitors", {}).items()
        if isinstance(v, dict)
    }


def record_enable(
    guard_key: str,
    *,
    enabled_at: str,
    baseline_expectancy: float,
    baseline_n: int,
    mode: str = "transition",
) -> dict:
    """Guard izlemeye alındı → izleme aç (MONITORING) + history(ARMED).

    `mode`:
      * "transition" — kapalı→açık geçişi; baseline guard-KAPALI penceresi →
        kanıtlı kıyas, oto-kapat hakkı VAR.
      * "adopted"    — zaten açık guard sonradan izlemeye alındı; baseline guard-AÇIK
        penceresi (eşzamanlı) → yalnız sürüklenme alarmı, oto-kapat YOK (recommend-only).
    """
    entry = {
        "guard_key": guard_key,
        "enabled_at": enabled_at,
        "baseline_expectancy": round(float(baseline_expectancy), 4),
        "baseline_n": int(baseline_n),
        "mode": mode,
        "status": "MONITORING",
    }
    data = load()
    data["monitors"][guard_key] = entry
    data["history"] = [{**entry, "event": "ARMED"}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return entry


def resolve(
    guard_key: str,
    *,
    outcome: str,
    post_expectancy: float,
    post_n: int,
    reason: str | None = None,
) -> dict | None:
    """İzlemeyi sonuçlandır (CONFIRMED veya ROLLED_BACK) ve slot'u temizle."""
    data = load()
    active = data.get("monitors", {}).get(guard_key)
    if not isinstance(active, dict):
        return None
    resolved = {
        **active,
        "status": outcome,
        "post_expectancy": round(float(post_expectancy), 4),
        "post_n": int(post_n),
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    if reason:
        resolved["reason"] = reason
    data["monitors"][guard_key] = None
    data["history"] = [{**resolved, "event": outcome}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return resolved


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]


__all__ = [
    "all_active",
    "get_active",
    "get_last_seen",
    "history",
    "load",
    "record_enable",
    "resolve",
    "set_last_seen",
]
