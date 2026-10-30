"""Operasyon alarmları: hiçbir hata sessiz kalmasın.

Hedef mimari 1. aşama (op_alerts). Öğrenme turunda koşar; `/system/health` ile
aynı parçaları (worker kalp atışı, son snapshot'ın sağlayıcı durumu) ve kota ile
yedek durum dosyalarını okur. Kural ihlalinde zile ``ops_alert`` bildirimi yazar;
aynı alarm ``OPS_ALERT_REPEAT_HOURS`` saatte bir hatırlatılır, düzelince bir kez
"düzeldi" bildirimi gider. Karar, boyut ve RiskGate'e etkisi yoktur.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

# "mock" gerçek bir kaynak değil: canlı fiyat eşlemesi olmayan sembol için
# tutulan işaret. Sağlık ekranında görünür kalır, alarm üretmez.
_NOT_A_SOURCE = {"mock"}


def _state_path() -> Path:
    return Path(os.environ.get("OPS_ALERTS_STATE_PATH", "data/runtime/ops_alerts_state.json"))


def _repeat() -> timedelta:
    try:
        return timedelta(hours=max(1, int(os.environ.get("OPS_ALERT_REPEAT_HOURS", "6"))))
    except ValueError:
        return timedelta(hours=6)


def _tick_slow_ms() -> int:
    try:
        return max(1000, int(os.environ.get("OPS_ALERT_TICK_SLOW_MS", "60000")))
    except ValueError:
        return 60000


def _parse(ts: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def collect(now: datetime | None = None) -> dict[str, dict[str, str]]:
    """Şu an ihlal edilen kurallar: anahtar → {priority, title, body}."""
    from packages.data import snapshot_store
    from packages.data.providers import quota
    from packages.ops import backup, system_health

    now = now or datetime.now(UTC)
    found: dict[str, dict[str, str]] = {}

    tick = system_health._worker_view(
        system_health.TICK_WORKER,
        system_health._stale_threshold("TICK_STALE_SEC", system_health.DEFAULT_TICK_STALE_SEC),
        now,
    )
    if tick.get("stale"):
        age = tick.get("age_seconds")
        found["tick_stale"] = {
            "priority": "critical",
            "title": "Tick durdu",
            "body": f"Son başarılı tick {int(age)} sn önce." if isinstance(age, (int, float)) else "Tick kalp atışı yok.",
        }
    elif isinstance(tick.get("duration_ms"), (int, float)) and tick["duration_ms"] > _tick_slow_ms():
        found["tick_slow"] = {
            "priority": "medium",
            "title": "Tick yavaşladı",
            "body": f"Son tur {int(tick['duration_ms']) // 1000} sn sürdü (sınır {_tick_slow_ms() // 1000} sn).",
        }

    latest = snapshot_store.latest() or {}
    dqs = latest.get("dqs") or {}
    summary = system_health._provider_summary(
        latest.get("provider_status") or {},
        decision_fallback_used=(bool(dqs.get("fallback_used")) if latest else None),
    )
    down = [name for name in summary.get("degraded_sources") or [] if name not in _NOT_A_SOURCE]
    if down:
        found["provider_degraded"] = {
            "priority": "high",
            "title": "Veri kaynağı sorunlu: " + ", ".join(sorted(down)),
            "body": "Karar yolundaki kaynak hata veriyor ya da bayat önbelleğe düştü.",
        }

    today = now.strftime("%Y-%m-%d")
    for name, row in quota.usage().items():
        per_day = int(row.get("per_day") or 0)
        if per_day > 0 and row.get("day") == today and int(row.get("count") or 0) >= per_day:
            found[f"quota:{name}"] = {
                "priority": "medium",
                "title": f"Ücretsiz kota doldu: {name}",
                "body": f"Bugünkü {per_day} çağrı hakkı bitti; UTC gece yarısı yenilenir, o zamana kadar önbellek ve yedek kaynak kullanılır.",
            }

    status = backup.read_status()
    last_ok = _parse(status.get("last_ok_at"))
    if status and (status.get("status") == "FAILED" or last_ok is None or now - last_ok > timedelta(hours=30)):
        found["backup"] = {
            "priority": "high",
            "title": "Durum yedeği alınamadı",
            "body": "; ".join((status.get("restore_check") or {}).get("errors") or status.get("unreadable") or [])[:200]
            or "Son başarılı yedek 30 saatten eski.",
        }
    return found


def _load_state() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def evaluate(now: datetime | None = None) -> dict[str, Any]:
    """Kuralları değerlendirir, gerekirse bildirim yazar; özet döner."""
    from packages.notifications import Notification, append_many, make_id

    now = now or datetime.now(UTC)
    found = collect(now)
    state = _load_state()
    out: list[Notification] = []

    def note(priority: str, title: str, body: str) -> None:
        out.append(Notification(
            id=make_id("ops_alert"), ts=now.isoformat(), type="ops_alert", priority=priority,
            title=title, body_short=body[:160], body_long=body,
        ))

    for key, alert in found.items():
        row = state.get(key) or {}
        last_sent = _parse(row.get("last_sent"))
        if not row.get("active"):
            note(alert["priority"], alert["title"], alert["body"])
            state[key] = {"active": True, "since": now.isoformat(), "last_sent": now.isoformat(), "title": alert["title"]}
        elif last_sent is None or now - last_sent >= _repeat():
            note(alert["priority"], alert["title"] + " (sürüyor)", alert["body"])
            row["last_sent"] = now.isoformat()
    for key, row in state.items():
        if row.get("active") and key not in found:
            note("low", "Düzeldi: " + str(row.get("title") or key), f"{row.get('since')} başlayan sorun giderildi.")
            row["active"] = False
            row["resolved_at"] = now.isoformat()

    append_many(out)
    write_text_atomic(_state_path(), json.dumps(state, ensure_ascii=False, indent=2))
    return {"active": sorted(found), "sent": len(out)}
