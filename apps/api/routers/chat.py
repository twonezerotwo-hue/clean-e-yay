"""POST /api/v1/chat — state-grounded soru-cevap (v2.6).

LLM karar vermez; yanıt her zaman mevcut backend state'ine dayanır.
Injection/bypass talepleri guard'da reddedilir; LLM yoksa deterministik
grounded yanıt döner. history yalnızca anlatım bağlamıdır (karar zincirine
girmez); son turlar LLM prompt'una taşınır.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
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
