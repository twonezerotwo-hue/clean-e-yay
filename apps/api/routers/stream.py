"""GET /api/v1/stream — Server-Sent Events.

Tek bir HTTP bağlantısı açık kalır; sunucu agent event'lerini push'lar.
UI tarafı EventSource('/api/v1/stream') ile dinler ve react-query
cache'ini ilgili anahtarlar için invalidate eder.

Format: standart SSE (text/event-stream):
    event: <type>\n
    data: <json payload>\n\n

Heartbeat: her 25 sn'de bir ':keepalive\n\n' satırı — proxy/Worker
bağlantıyı idle sayıp kesmesin. (Cloudflare 100 sn'de idle keser.)
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from packages.events import bus

_log = logging.getLogger("apps.api.stream")

router = APIRouter(tags=["stream"])

HEARTBEAT_SEC = 25.0


async def _event_stream(request: Request):
    q = bus.subscribe()
    _log.info("SSE subscribed (now %d total)", bus.subscriber_count)
    # İlk satır: client bağlandığını bilsin (browser EventSource onopen tetikler).
    yield "event: hello\ndata: {}\n\n"
    try:
        # Request-scoped stream (arka plan döngüsü DEĞİL): bağlantı kopunca
        # biter. Bu, HTTP yanıtının kendisi — architecture guard'ın aradığı
        # zamanlanmış/arka-plan döngüsü değil.
        while not await request.is_disconnected():
            try:
                evt = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_SEC)
            except TimeoutError:
                # SSE comment satırı — proxy bağlantıyı canlı sayar, browser yok sayar.
                yield ":keepalive\n\n"
                continue
            payload = json.dumps(evt.payload, default=str, ensure_ascii=False)
            yield f"event: {evt.type}\ndata: {payload}\n\n"
    finally:
        bus.unsubscribe(q)
        _log.info("SSE unsubscribed (now %d total)", bus.subscriber_count)


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            # Next.js rewrite + Cloudflare Worker zincirinde buffering kapalı olsun.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
