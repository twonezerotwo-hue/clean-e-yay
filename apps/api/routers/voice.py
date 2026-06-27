"""POST /api/voice/speak - high quality text-to-speech proxy.

This route is intentionally separate from the trading decision API. It never
reads or mutates decision state; it only turns caller-provided text into audio.
"""
from __future__ import annotations

import asyncio
import os
from typing import Protocol

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["voice"])

MAX_TTS_CHARS = 4000
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_EDGE_TTS_VOICE = "tr-TR-EmelNeural"


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


class EdgeTTSProvider:
    """Microsoft Edge public TTS — free, no API key, no quota."""

    def __init__(self) -> None:
        self.default_voice = (
            os.environ.get("EDGE_TTS_VOICE", "").strip() or DEFAULT_EDGE_TTS_VOICE
        )

    def speak(self, text: str, voice: str | None = None) -> bytes:
        import edge_tts

        async def _run() -> bytes:
            chunks = bytearray()
            communicate = edge_tts.Communicate(text, voice or self.default_voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        try:
            audio = asyncio.run(_run())
        except Exception as exc:  # edge_tts raises its own error types over the network
            raise HTTPException(
                status_code=503,
                detail=f"Edge TTS request failed: {exc.__class__.__name__}",
            ) from exc
        if not audio:
            raise HTTPException(status_code=503, detail="Edge TTS returned no audio.")
        return audio


def get_tts_provider(name: str | None) -> TTSProvider:
    provider = (name or os.environ.get("TTS_PROVIDER") or "elevenlabs").strip().lower()
    if provider == "elevenlabs":
        return ElevenLabsTTSProvider()
    if provider == "edge":
        return EdgeTTSProvider()
    raise HTTPException(status_code=503, detail=f"Unsupported TTS provider: {provider}")


@router.post("/voice/speak")
def speak(req: VoiceSpeakRequest) -> Response:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")

    primary = req.provider or os.environ.get("TTS_PROVIDER") or "elevenlabs"
    try:
        audio = get_tts_provider(primary).speak(text=text, voice=req.voice)
    except HTTPException:
        # Ücretli sağlayıcı kota/hata verirse, ücretsiz Edge TTS'e otomatik düş —
        # kullanıcı tarayıcı sesine düşmeden önce hâlâ kaliteli bir ses alır.
        if primary.strip().lower() == "edge":
            raise
        audio = EdgeTTSProvider().speak(text=text, voice=None)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )
