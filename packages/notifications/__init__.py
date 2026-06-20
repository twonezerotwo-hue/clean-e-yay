"""Notification module — append-only JSONL log + read/ack.

Mimari: salt-gözlemleyici. Karar vermez, state'i mutate etmez. Her bildirim
deterministic kurallarla `detector.py`'da tetiklenir; bu modül yalnız depolar
ve sunar.

Depolama: `data/runtime/notifications.jsonl` — son 200 saklı (rotation),
PAPER_SAFE, gitignored. Yeniden başlatmada okunur.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NOTIFICATIONS_PATH = Path(
    os.environ.get("NOTIFICATIONS_PATH", "data/runtime/notifications.jsonl")
)
MAX_NOTIFICATIONS = 200

_LOCK = threading.Lock()

Priority = str  # "critical" | "high" | "medium" | "low"
NotificationType = str
# Sabit enum (string olarak — kanonik):
#   ticket_created · ticket_expiring · ticket_expired · ticket_blocked
#   recheck_exit_recommend · recheck_reduce
#   risk_gate_changed · risk_kill_switch
#   catalyst_imminent · dqs_dropped
#   position_near_sl · position_near_tp


@dataclass
class Notification:
    id: str
    ts: str
    type: NotificationType
    priority: Priority
    title: str
    body_short: str
    body_long: str
    ticket_id: str | None = None
    position_id: str | None = None
    actions: list[dict[str, str]] = field(default_factory=list)
    ack: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_all() -> list[Notification]:
    if not NOTIFICATIONS_PATH.exists():
        return []
    out: list[Notification] = []
    try:
        for line in NOTIFICATIONS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(Notification(
                    id=str(d.get("id", "")),
                    ts=str(d.get("ts", "")),
                    type=str(d.get("type", "")),
                    priority=str(d.get("priority", "medium")),
                    title=str(d.get("title", "")),
                    body_short=str(d.get("body_short", "")),
                    body_long=str(d.get("body_long", "")),
                    ticket_id=d.get("ticket_id"),
                    position_id=d.get("position_id"),
                    actions=list(d.get("actions", [])),
                    ack=bool(d.get("ack", False)),
                ))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    except OSError:
        return []
    return out


def _write_all(items: list[Notification]) -> None:
    NOTIFICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTIFICATIONS_PATH.with_name(f"{NOTIFICATIONS_PATH.name}.tmp-{os.getpid()}")
    payload = "\n".join(json.dumps(n.to_dict(), default=str) for n in items[-MAX_NOTIFICATIONS:])
    tmp.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    os.replace(tmp, NOTIFICATIONS_PATH)


def append(notif: Notification) -> None:
    """Yeni bildirim ekle (rotate son MAX_NOTIFICATIONS)."""
    with _LOCK:
        items = _read_all()
        items.append(notif)
        _write_all(items)


def append_many(notifs: list[Notification]) -> None:
    if not notifs:
        return
    with _LOCK:
        items = _read_all()
        items.extend(notifs)
        _write_all(items)


def list_recent(limit: int = 50, unread_only: bool = False) -> list[Notification]:
    with _LOCK:
        items = _read_all()
    if unread_only:
        items = [n for n in items if not n.ack]
    return items[-limit:][::-1]  # newest first


def unread_count() -> int:
    with _LOCK:
        return sum(1 for n in _read_all() if not n.ack)


def mark_ack(notif_id: str) -> bool:
    with _LOCK:
        items = _read_all()
        for n in items:
            if n.id == notif_id:
                n.ack = True
                _write_all(items)
                return True
    return False


def mark_all_ack() -> int:
    with _LOCK:
        items = _read_all()
        n = sum(1 for x in items if not x.ack)
        for x in items:
            x.ack = True
        _write_all(items)
        return n


def make_id(type_: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"notif_{ts}_{type_}"


__all__ = [
    "Notification",
    "append",
    "append_many",
    "list_recent",
    "unread_count",
    "mark_ack",
    "mark_all_ack",
    "make_id",
]
