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

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from packages.ops.store import append_jsonl_rotating, read_jsonl_tail

DEFAULT_PATH = "data/runtime/paper_audit.jsonl"
DEFAULT_MAX_READ = 200
DEFAULT_MAX_BYTES = 32 * 1024 * 1024

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
        append_jsonl_rotating(p, event, max_bytes=DEFAULT_MAX_BYTES)
    except OSError:
        pass  # audit ASLA lifecycle'ı kesmez
    return event


def read_recent(limit: int = DEFAULT_MAX_READ) -> list[dict]:
    """Son `limit` audit olayı (en yeni en sonda); bozuk satır atlanır."""
    # B12 — dosyanın yalnız sonu okunur (append-only günlük sınırsız büyür).
    return read_jsonl_tail(_path(), limit)


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


_CLOSE_ACTIONS = ("CLOSED", "KILL_SWITCH_EXIT", "RISK_REDUCE_EXIT", "TIME_STOP_EXPIRED")
_CLOSED_CACHE: dict = {"key": None, "ids": frozenset()}


def closed_trade_ids() -> set[str]:
    """Değişmez kapanış olayı olan işlem kimlikleri — günlüğün tamamı (döndürülmüş
    `.1` arşivi dahil) taranır; kimlik `trade_id`, eski kayıtlarda `position_id`
    (tam kapanışta işlem kimliğiyle aynı). Dosya boyutu/zamanına göre önbellekli;
    yalnız kapanış satırları ayrıştırılır."""
    import json

    path = _path()
    files = [f for f in (path.with_name(path.name + ".1"), path) if f.exists()]
    try:
        key = tuple((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files)
    except OSError:
        return set()
    if _CLOSED_CACHE["key"] == key:
        return set(_CLOSED_CACHE["ids"])
    ids: set[str] = set()
    for f in files:
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not any(f'"{a}"' in line for a in _CLOSE_ACTIONS):
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("action") in _CLOSE_ACTIONS:
                        trade_id = event.get("trade_id") or event.get("position_id")
                        if trade_id:
                            ids.add(str(trade_id))
        except OSError:
            continue
    _CLOSED_CACHE["key"], _CLOSED_CACHE["ids"] = key, frozenset(ids)
    return ids


__all__ = ["ACTIONS", "closed_trade_ids", "read_recent", "record", "summary"]
