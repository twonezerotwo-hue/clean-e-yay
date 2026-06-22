"""POST /api/voice/speak - high quality text-to-speech proxy.

This route is intentionally separate from the trading decision API. It never
reads or mutates decision state; it only turns caller-provided text into audio.
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["voice"])

MAX_TTS_CHARS = 4000
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"


class VoiceSpeakRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_CHARS)
    voice: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=32)


class TTSProvider(Protocol):
    def speak(self, text: str, voice: str | None = None) -> bytes:
        """Return MPEG audio bytes for text."""


class ElevenLabsTTSProvider:
    def __init__(self) -> None:
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.default_voice_id = (
            os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
            or DEFAULT_ELEVENLABS_VOICE_ID
        )
        self.model_id = (
            os.environ.get("ELEVENLABS_MODEL_ID", "").strip()
            or DEFAULT_ELEVENLABS_MODEL_ID
        )

    def speak(self, text: str, voice: str | None = None) -> bytes:
        if not self.api_key:
            raise HTTPException(
                status_code=503,
                detail="ELEVENLABS_API_KEY is not configured.",
            )

        voice_id = (voice or self.default_voice_id).strip()
        if not voice_id:
            raise HTTPException(
                status_code=503,
                detail="ELEVENLABS_VOICE_ID is not configured.",
            )

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.44,
                "similarity_boost": 0.78,
                "style": 0.28,
                "use_speaker_boost": True,
            },
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    url,
                    headers={
                        "accept": "audio/mpeg",
                        "content-type": "application/json",
                        "xi-api-key": self.api_key,
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"TTS provider request failed: {exc.__class__.__name__}",
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=503,
                detail=f"TTS provider rejected request: HTTP {response.status_code}",
            )
        return response.content


def get_tts_provider(name: str | None) -> TTSProvider:
    provider = (name or os.environ.get("TTS_PROVIDER") or "elevenlabs").strip().lower()
    if provider == "elevenlabs":
        return ElevenLabsTTSProvider()
    raise HTTPException(status_code=503, detail=f"Unsupported TTS provider: {provider}")


@router.post("/voice/speak")
def speak(req: VoiceSpeakRequest) -> Response:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")

    audio = get_tts_provider(req.provider).speak(text=text, voice=req.voice)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
