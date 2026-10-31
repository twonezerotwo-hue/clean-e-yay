"""POST /api/voice/speak — local VoiceStudio speech for E-YAY.

Briefings, chat and notifications share one voice: the configured VoiceStudio
profile. There is no Piper, cloud, browser-TTS or implicit voice fallback.
Voice synthesis is presentation-only and cannot influence trading decisions.
"""
from __future__ import annotations

import http.client
import json
import math
import os
import re
import socket
import unicodedata
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["voice"])

MAX_TTS_CHARS = 4000
MAX_WAV_BYTES = 64 * 1024 * 1024
DEFAULT_VOICESTUDIO_URL = "http://127.0.0.1:3900/v1/audio/speech"
DEFAULT_VOICESTUDIO_VOICE = "türkçe voice 1"


def normalize_voice_text(value: str) -> str:
    """Preserve Turkish NFC characters, removing invisible separators."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("i\u0307", "i")
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class VoiceSpeakRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_CHARS)
    # Legacy frontend fields are accepted but cannot override the single
    # configured local engine or speaker profile.
    voice: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=32)


def _local_voice_endpoint() -> tuple[str, int, str]:
    url = os.environ.get("VOICESTUDIO_API_URL", DEFAULT_VOICESTUDIO_URL).strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port or 80
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Invalid VoiceStudio URL configuration.") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.path != "/v1/audio/speech"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(
            status_code=503,
            detail="VoiceStudio must use its local /v1/audio/speech endpoint.",
        )
    return parsed.hostname, port, parsed.path


class VoiceStudioTTSProvider:
    """Use the locally installed VoiceStudio process, without remote fallback."""

    def __init__(self) -> None:
        self.host, self.port, self.path = _local_voice_endpoint()
        self.voice = os.environ.get("VOICESTUDIO_VOICE", DEFAULT_VOICESTUDIO_VOICE).strip()
        self.model = os.environ.get("VOICESTUDIO_MODEL", "tts-1").strip()
        try:
            self.speed = float(os.environ.get("VOICESTUDIO_SPEED", "0.85"))
            self.timeout = float(os.environ.get("VOICESTUDIO_TIMEOUT_SEC", "180"))
        except ValueError as exc:
            raise HTTPException(status_code=503, detail="Invalid VoiceStudio numeric configuration.") from exc
        if (
            not self.voice
            or not self.model
            or not math.isfinite(self.speed)
            or not 0.25 <= self.speed <= 2.0
            or not math.isfinite(self.timeout)
            or not 10 <= self.timeout <= 600
        ):
            raise HTTPException(status_code=503, detail="Invalid VoiceStudio configuration.")

    def speak(self, text: str, voice: str | None = None) -> bytes:
        del voice  # Only VOICESTUDIO_VOICE determines the local speaker.
        payload = json.dumps(
            {
                "model": self.model,
                "voice": self.voice,
                "input": text,
                "speed": self.speed,
                "response_format": "wav",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(
                "POST",
                self.path,
                body=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "audio/wav",
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise HTTPException(
                    status_code=503,
                    detail=f"VoiceStudio local TTS returned HTTP {response.status}.",
                )
            audio = response.read(MAX_WAV_BYTES + 1)
        except (TimeoutError, socket.timeout) as exc:
            raise HTTPException(status_code=504, detail="VoiceStudio TTS timed out.") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise HTTPException(status_code=503, detail="VoiceStudio local TTS is unavailable.") from exc
        finally:
            connection.close()

        if len(audio) > MAX_WAV_BYTES:
            raise HTTPException(status_code=502, detail="VoiceStudio returned oversized audio.")
        if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise HTTPException(status_code=502, detail="VoiceStudio returned invalid WAV audio.")
        return audio


def get_tts_provider(name: str | None = None) -> VoiceStudioTTSProvider:
    del name
    return VoiceStudioTTSProvider()


@router.post("/voice/speak")
def speak(req: VoiceSpeakRequest) -> Response:
    text = normalize_voice_text(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    audio = get_tts_provider().speak(text=text, voice=req.voice)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Voice-Provider": "voicestudio-local"},
    )
