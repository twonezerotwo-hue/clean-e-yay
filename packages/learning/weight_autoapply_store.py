"""G3 — otomatik-uygulanan ağırlık değişiklikleri için baseline + rollback ledger'i.

Dar bantta otomatik uygulanan bir rebalance'ı izlemek için gereken durumu tutar:
hangi versiyon uygulandı, öncesinde manifest neydi (geri almak için), uygulama
anındaki baseline expectancy + örnek sayısı. learning_worker apply sonrası yeterli
yeni outcome biriktiğinde `weight_rollback.check_rollback()` ile karşılaştırır;
sonuç CONFIRMED ya da ROLLED_BACK olur ve `active` temizlenir.

Aynı anda yalnız BİR aktif izlenen değişiklik olur (rebalance_store.maybe_auto_apply
buna bakar) — böylece otonom uygulama "tek-değişiklik-tek-doğrulama" disiplininde
kalır, zincirleme/çakışan apply olmaz.

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
    p = Path(os.environ.get("WEIGHT_AUTOAPPLY_PATH", "data/runtime/weight_autoapply.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _empty() -> dict:
    return {"active": None, "history": []}


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
    data.setdefault("active", None)
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


def get_active() -> dict | None:
    """İzlenen (henüz CONFIRMED/ROLLED_BACK olmamış) auto-apply varsa döner."""
    return load().get("active")


def record_apply(
    *,
    applied_version: str,
    prev_version: str,
    prev_manifest: dict | None,
    baseline_expectancy: float,
    baseline_n: int,
    regime: str | None,
    deltas: list | None,
    applied_at: str | None = None,
) -> dict:
    """Otomatik uygulamayı kaydet → `active` (MONITORING) + history(AUTO_APPLIED).

    `prev_manifest` rollback için saklanır (None ise geri alış = manifest'i sil →
    baseline v1.0.0'a düş)."""
    applied_at = applied_at or datetime.now(UTC).isoformat()
    entry = {
        "applied_version": applied_version,
        "prev_version": prev_version,
        "prev_manifest": prev_manifest,
        "baseline_expectancy": round(float(baseline_expectancy), 4),
        "baseline_n": int(baseline_n),
        "regime": regime,
        "deltas": deltas or [],
        "applied_at": applied_at,
        "status": "MONITORING",
    }
    data = load()
    data["active"] = entry
    data["history"] = [{**entry, "event": "AUTO_APPLIED"}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return entry


def resolve_active(*, outcome: str, post_expectancy: float, post_n: int) -> dict | None:
    """Aktif izlemeyi sonuçlandır (CONFIRMED veya ROLLED_BACK) ve `active`'i temizle."""
    data = load()
    active = data.get("active")
    if not active:
        return None
    resolved = {
        **active,
        "status": outcome,
        "post_expectancy": round(float(post_expectancy), 4),
        "post_n": int(post_n),
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    data["active"] = None
    data["history"] = [{**resolved, "event": outcome}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return resolved


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]


__all__ = [
    "get_active",
    "history",
    "load",
    "record_apply",
    "resolve_active",
]
