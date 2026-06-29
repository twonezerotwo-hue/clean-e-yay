"""Minimal in-process pub/sub bus — thread-safe.

Tasarım kararları:
- asyncio.Queue per subscriber → yavaş abone diğerlerini yavaşlatmaz.
- maxsize=256: bir abone bu kadar event biriktirirse en eski drop edilir.
- publish() THREAD-SAFE: subscribe sırasında o anki event-loop yakalanır;
  publish farklı thread'den çağrıldığında loop.call_soon_threadsafe ile
  marshal edilir. Bu olmadan learning_worker (asyncio.to_thread içinde
  çalışır) ya da herhangi bir sync code path notifications.append'i
  tetiklediğinde, asyncio.Queue.put_nowait kararsız davranıyor (Windows'ta
  process'i kilitleyebiliyor — pratikte gözlendi).
- Loop yoksa (test, salt-sync ortam) publish sessizce no-op.
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


class _Sub:
    __slots__ = ("loop", "queue")

    def __init__(self, queue: asyncio.Queue[Event], loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop


class EventBus:
    def __init__(self, *, queue_size: int = 256) -> None:
        self._subs: set[_Sub] = set()
        self._queue_size = queue_size

    def subscribe(self) -> asyncio.Queue[Event]:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subs.add(_Sub(q, loop))
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subs = {s for s in self._subs if s.queue is not q}

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, type: str, payload: dict[str, Any] | None = None) -> None:
        if not self._subs:
            return
        evt = Event(type=type, payload=payload or {})
        for sub in list(self._subs):
            self._deliver(sub, evt)

    @staticmethod
    def _deliver(sub: _Sub, evt: Event) -> None:
        loop = sub.loop
        if not loop.is_running():
            return
        # call_soon_threadsafe; loop ister aynı thread'de ister başka, güvenli.
        try:
            loop.call_soon_threadsafe(EventBus._enqueue, sub.queue, evt)
        except RuntimeError:
            # Loop kapanmış olabilir — abone az sonra unsubscribe edecek.
            pass

    @staticmethod
    def _enqueue(q: asyncio.Queue[Event], evt: Event) -> None:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            # Yavaş abone: en eskiyi at, yeniyi koy.
            try:
                q.get_nowait()
                q.put_nowait(evt)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


# Process-wide singleton. Test'lerde override edilebilir.
bus = EventBus()
