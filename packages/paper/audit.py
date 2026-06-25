"""P1 — paper lifecycle audit trail (append-only JSONL).

Her lifecycle olayı (open/close/skip/blocked/kill-switch/state-repair) tek
satır JSON olarak `data/runtime/paper_audit.jsonl`'a yazılır. Amaç: paper
yaşam döngüsünü **audit edilebilir** kılmak.

PAPER_SAFE / NO_EXECUTION: audit yalnızca KAYIT tutar — emir üretmez, state
değiştirmez, karar vermez ve **asla çağıranı patlatmaz** (best-effort; yazım
hatası yutulur, lifecycle kesilmez). Okuma korumalı: bozuk satır atlanır.

Atomiklik: tek satırlık append (`a` modu) POSIX yerel dosya sisteminde küçük
yazımlar için atomiktir; yarım satır bırakmamak için satır tek `write` ile
yazılır.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = "data/runtime/paper_audit.jsonl"
DEFAULT_MAX_READ = 200

# Bilinen audit aksiyonları (openapi enum ile senkron tutulur).
ACTIONS = (
    "OPEN_ATTEMPT",
    "OPENED",
    "OPEN_BLOCKED",
    "SIZE_REDUCED",
    "TIME_STOP_EXPIRED",
    "EXIT_PENDING",
    "CLOSED",
    "KILL_SWITCH_EXIT",
    "RISK_REDUCE_EXIT",
    "MANUAL_RISK_PLAN_UPDATE",
    "STATE_REPAIRED",
    "ERROR",
)


def _path() -> Path:
    return Path(os.environ.get("PAPER_AUDIT_PATH", DEFAULT_PATH))


def record(action: str, **fields: object) -> dict:
    """Audit olayı oluştur + diske ekle; olay dict'ini döner (best-effort).

    None alanlar yazılmaz (gürültü azaltma). Yazım hatası yutulur.
    """
    event: dict = {
        "event_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
    }
    for k, v in fields.items():
        if v is not None:
            event[k] = v
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # audit ASLA lifecycle'ı kesmez
    return event


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` audit olayı (en yeni en sonda); bozuk satır atlanır."""
    p = _path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # bozuk satır atlanır (crash yok)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def summary(limit: int = DEFAULT_MAX_READ) -> dict:
    """Audit özeti — panel için (son `limit` pencerede action sayıları)."""
    events = read_recent(limit)
    counts: dict[str, int] = {}
    for e in events:
        a = str(e.get("action", "UNKNOWN"))
        counts[a] = counts.get(a, 0) + 1
    return {
        "window_events": len(events),
        "counts": counts,
        "last_event_at": events[-1].get("timestamp") if events else None,
    }


__all__ = ["ACTIONS", "read_recent", "record", "summary"]
