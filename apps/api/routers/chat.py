"""POST /api/v1/chat — state-grounded soru-cevap (v2.6).

LLM karar vermez; yanıt her zaman mevcut backend state'ine dayanır.
Injection/bypass talepleri guard'da reddedilir; LLM yoksa deterministik
grounded yanıt döner.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.agent.llm import chat as llm_chat
from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.data.provenance import data_provenance

router = APIRouter(tags=["ai"])

MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


@router.post("/chat")
def post_chat(req: ChatRequest) -> dict:
    result = llm_chat.answer(req.message)
    result["mode"] = data_provenance(get_cached_snapshot())
    return result
