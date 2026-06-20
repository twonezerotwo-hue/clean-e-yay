"""Minimal in-process pub/sub bus.

Tasarım kararları:
- asyncio.Queue per subscriber → yavaş abone diğerlerini yavaşlatmaz.
- maxsize=256: bir abone bu kadar event biriktirirse en eski drop edilir
  (UI tarafı yine sonraki event'te güncel state'i çeker; data loss
  felaket değil, sadece "5 sn'den eski 'nabız' atışı"nı kaybedebilir).
- Senkron publish → çağıran kod (tick_worker) await etmez, fire-and-forget.
- Thread-safe DEĞİL — sadece event-loop'tan çağrılmalı. tick_worker zaten
  asyncio task, learning_worker run_thread sarmalı.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("packages.events")


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, *, queue_size: int = 256) -> None:
        self._subs: set[asyncio.Queue[Event]] = set()
        self._queue_size = queue_size

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subs.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, type: str, payload: dict[str, Any] | None = None) -> None:
        if not self._subs:
            return
        evt = Event(type=type, payload=payload or {})
        for q in list(self._subs):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                # Yavaş abone: en eskiyi at, yeniyi koy. UI yine bir sonraki
                # event'te tutarlı state'e gelir.
                try:
                    q.get_nowait()
                    q.put_nowait(evt)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


# Process-wide singleton. Test'lerde override edilebilir.
bus = EventBus()
