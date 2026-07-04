"""POST /api/v1/chat — state-grounded soru-cevap (v2.6) + /chat/stream SSE (v2.8).

LLM karar vermez; yanıt her zaman mevcut backend state'ine dayanır.
Injection/bypass talepleri guard'da reddedilir; LLM yoksa deterministik
grounded yanıt döner. history yalnızca anlatım bağlamıdır (karar zincirine
girmez); son turlar LLM prompt'una taşınır.

/chat/stream: aynı iş mantığı (llm_chat.stream_answer), SSE çerçevelerinde.
Endpoint ve generator BİLEREK sync def — Starlette threadpool'da iterate eder;
async def içinde blocking urllib (Groq/Ollama stream'i) event loop'u kilitlerdi.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.agent.llm import chat as llm_chat
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance

router = APIRouter(tags=["ai"])

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 12
MAX_TURN_CHARS = 500


class ChatTurn(BaseModel):
    role: Literal["user", "agent"]
    text: str = Field(min_length=1, max_length=MAX_TURN_CHARS)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatTurn] | None = Field(default=None, max_length=MAX_HISTORY_TURNS)


@router.post("/chat")
def post_chat(req: ChatRequest) -> dict:
    history = [t.model_dump() for t in (req.history or [])]
    result = llm_chat.answer(req.message, history=history)
    result["mode"] = data_provenance(get_cached_snapshot())
    return result


def _sse_frame(event: str, payload: dict) -> str:
    data = json.dumps(payload, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def _chat_sse(message: str, history: list[dict]) -> Iterator[str]:
    try:
        for event, payload in llm_chat.stream_answer(message, history=history):
            if event == "done":
                # post_chat ile simetrik: provenance bloğu son cevaba eklenir.
                payload["mode"] = data_provenance(get_cached_snapshot())
            yield _sse_frame(event, payload)
    except Exception as exc:  # akış ortası crash istemciye error eventi olarak taşınmalı
        yield _sse_frame("error", {"message": str(exc)})


@router.post("/chat/stream")
def post_chat_stream(req: ChatRequest) -> StreamingResponse:
    history = [t.model_dump() for t in (req.history or [])]
    return StreamingResponse(
        _chat_sse(req.message, history),
        media_type="text/event-stream",
        headers={
            # Next.js rewrite + proxy zincirinde buffering kapalı (stream.py ile aynı).
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
