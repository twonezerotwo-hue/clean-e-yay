"""CP4 slice 2 — otomatik-uygulanan TF-target (SL/TP geometri) için outcome-bazlı
rollback denetimi. Ağırlık tarafındaki `weight_autoapply_store` + `weight_rollback`
deseninin geometri ikizi.

Geometri auto-apply (tf_target_store ±%15 bant) şimdiye kadar **rollback'siz**di:
kötü bir nudge expectancy'i düşürse bile geri alınmıyordu (ağırlıklarda G3 vardı,
geometride yoktu). Bu modül o boşluğu kapatır:

  * Bir veya daha çok TF auto-apply edildiğinde `record_apply()` → active(MONITORING)
    + apply anındaki eşleştirilmiş baseline expectancy (weight_rollback.pre_apply).
  * learning_worker her koşuda `check_rollback()` çağırır: apply'dan SONRA AÇILAN
    verified outcome'lar ≥ eşik olunca post-apply expectancy'i baseline ile kıyaslar.
      - post < baseline → ROLLED_BACK: tf_target_store.revert_overrides(prev) ile
        geometri önceki değerine döner.
      - post ≥ baseline → CONFIRMED.
  * Sonsuz bekleme koruması: izleme çok eskiyse güvenli tarafta kapatılır (kanıt
    yoksa revert). Aynı anda yalnız BİR aktif izleme (tek-değişiklik-tek-doğrulama).

Expectancy pencereleri weight_rollback'ten REUSE edilir (tek kaynak; eşleştirilmiş
opened_at>applied_at mantığı orada). PAPER_SAFE / NO_EXECUTION: yalnız SL/TP geometri
override'larını geri alır; emir üretmez.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import REPO_ROOT
from packages.learning import tf_target_store, weight_rollback

_LOCK = threading.Lock()
_HISTORY_CAP = 100
_MIN_OUTCOMES_DEFAULT = 15
_MONITOR_MAX_AGE_HOURS_DEFAULT = 336.0  # 14 gün; 0 → süre koruması kapalı


def _store_path() -> Path:
    p = Path(os.environ.get("TF_TARGET_AUTOAPPLY_PATH", "data/runtime/tf_target_autoapply.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("TF_TARGET_ROLLBACK_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _monitor_max_age_hours() -> float:
    try:
        return max(0.0, float(os.environ.get(
            "TF_TARGET_MONITOR_MAX_AGE_HOURS", _MONITOR_MAX_AGE_HOURS_DEFAULT)))
    except (TypeError, ValueError):
        return _MONITOR_MAX_AGE_HOURS_DEFAULT


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
    return load().get("active")


def record_apply(
    *,
    prev_overrides: dict[str, dict[str, float]],
    applied_tfs: list[str],
    baseline_expectancy: float,
    baseline_n: int,
    applied_at: str | None = None,
) -> dict:
    """Geometri auto-apply'ını izlemeye al. `prev_overrides` = revert hedefi
    ({tf: {param: eski_değer}}, boş dict → config default'a düş)."""
    applied_at = applied_at or datetime.now(UTC).isoformat()
    entry = {
        "applied_tfs": list(applied_tfs),
        "prev_overrides": prev_overrides or {},
        "baseline_expectancy": round(float(baseline_expectancy), 4),
        "baseline_n": int(baseline_n),
        "applied_at": applied_at,
        "status": "MONITORING",
    }
    data = load()
    data["active"] = entry
    data["history"] = [{**entry, "event": "AUTO_APPLIED"}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return entry


def _resolve(active: dict, *, outcome: str, post_exp: float, post_n: int,
             reason: str | None = None) -> dict:
    resolved = {
        **active, "status": outcome,
        "post_expectancy": round(float(post_exp), 4), "post_n": int(post_n),
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    if reason:
        resolved["reason"] = reason
    data = load()
    data["active"] = None
    data["history"] = [{**resolved, "event": outcome}, *data.get("history", [])][:_HISTORY_CAP]
    _save(data)
    return resolved


def _decide(active: dict, *, post_exp: float, post_n: int, baseline: float,
            reason: str | None = None) -> dict:
    """post < baseline → ROLLED_BACK (geometriyi geri al); aksi CONFIRMED."""
    if post_exp < baseline:
        tf_target_store.revert_overrides(active.get("prev_overrides") or {})
        out = _resolve(active, outcome="ROLLED_BACK", post_exp=post_exp, post_n=post_n,
                       reason=reason)
        out["reverted_tfs"] = list(active.get("applied_tfs") or [])
    else:
        out = _resolve(active, outcome="CONFIRMED", post_exp=post_exp, post_n=post_n,
                       reason=reason)
        out["confirmed_tfs"] = list(active.get("applied_tfs") or [])
    out["baseline_expectancy"] = baseline
    return out


def check_rollback() -> dict:
    """İzlenen geometri auto-apply'ı değerlendir. Durum: no_active | monitoring |
    CONFIRMED | ROLLED_BACK. Defensive (worker patlamamalı)."""
    active = get_active()
    if not active:
        return {"status": "no_active"}

    need = _min_outcomes()
    applied_at = str(active.get("applied_at") or "")
    post_n, post_exp = weight_rollback.post_open_expectancy(applied_at)
    baseline = float(active.get("baseline_expectancy", 0.0))

    if post_n < need:
        max_age = _monitor_max_age_hours()
        age_h = None
        dt = weight_rollback._parse_dt(applied_at)
        if dt is not None:
            age_h = (datetime.now(UTC) - dt).total_seconds() / 3600.0
        if max_age > 0 and age_h is not None and age_h >= max_age:
            if post_n == 0:
                tf_target_store.revert_overrides(active.get("prev_overrides") or {})
                out = _resolve(active, outcome="ROLLED_BACK", post_exp=post_exp,
                               post_n=post_n, reason="monitor_expired_no_evidence")
                out["reverted_tfs"] = list(active.get("applied_tfs") or [])
                out["baseline_expectancy"] = baseline
                return out
            return _decide(active, post_exp=post_exp, post_n=post_n, baseline=baseline,
                           reason="monitor_expired_partial")
        return {"status": "monitoring", "post_n": post_n, "need": need}

    return _decide(active, post_exp=post_exp, post_n=post_n, baseline=baseline)


def history(limit: int = 20) -> list[dict]:
    return load().get("history", [])[:limit]


__all__ = [
    "check_rollback",
    "get_active",
    "history",
    "load",
    "record_apply",
]
