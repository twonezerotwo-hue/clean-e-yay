"""In-process event bus for fanout pub/sub.

Tek process içinde "şu kanala biri abone mi, varsa de ki" pattern'i. SSE
endpoint'i abone olur, agent kodu publish eder. asyncio.Queue tabanlı; her
abone kendi sırasında biriktirir, yavaş aboneler diğer aboneleri yavaşlatmaz.
"""
from .bus import EventBus, bus

__all__ = ["EventBus", "bus"]
