"""POST /api/voice/speak - high quality text-to-speech proxy.

This route is intentionally separate from the trading decision API. It never
reads or mutates decision state; it only turns caller-provided text into audio.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["voice"])

MAX_TTS_CHARS = 4000
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_EDGE_TTS_VOICE = "tr-TR-EmelNeural"
GOOGLE_TTS_ENDPOINT = "https://translate.google.com/translate_tts"
GOOGLE_TTS_CHUNK_CHARS = 180
DEFAULT_PIPER_MODEL = "tr_TR-dfki-medium.onnx"

# Ücretli sağlayıcı kota/faturalama hatası (ör. ElevenLabs 402 kredi bitti)
# alınca bu süre boyunca onu hiç denemeyiz — her okumada önce deneyip Edge'e
# düşmek 4 sn gecikme ekliyordu. Süre sonunda yeniden denenir (kredi yenilenebilir).
_QUOTA_COOLDOWN_SEC = 3600.0
_elevenlabs_skip_until = 0.0


class TTSQuotaError(HTTPException):
    """Ücretli TTS sağlayıcı kota/faturalama hatası (upstream 401/402/429)."""

    def __init__(self, upstream_status: int) -> None:
        super().__init__(
            status_code=503,
            detail=f"TTS provider quota exhausted: HTTP {upstream_status}",
        )
        self.upstream_status = upstream_status


class VoiceSpeakRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_CHARS)
    voice: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=32)


class TTSProvider(Protocol):
    def speak(self, text: str, voice: str | None = None) -> bytes:
        """Return playable audio bytes for text (WAV or MPEG)."""


class PiperTTSProvider:
    """Local Turkish Piper voice.

    Piper is deliberately invoked as an isolated executable instead of being
    imported into the API environment. This keeps the decision/LLM dependency
    graph unchanged while making every local voice request offline-capable.
    """

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[3]
        configured_model = os.environ.get("PIPER_MODEL", "").strip()
        self.model = Path(configured_model) if configured_model else root / "data" / "models" / "piper" / DEFAULT_PIPER_MODEL
        if not self.model.is_absolute():
            self.model = root / self.model

        configured_bin = os.environ.get("PIPER_BIN", "").strip()
        candidates = [
            Path(configured_bin) if configured_bin else None,
            Path(sys.executable).with_name("piper.exe"),
            root / ".voice-venv" / "Scripts" / "piper.exe",
            root / ".voice-venv" / "bin" / "piper",
        ]
        self.binary = next(
            (candidate for candidate in candidates if candidate and candidate.exists()),
            Path(shutil.which("piper") or "piper"),
        )

    def speak(self, text: str, voice: str | None = None) -> bytes:
        del voice  # Piper model already contains the Turkish speaker.
        if not self.binary.exists() and self.binary.name != "piper":
            raise HTTPException(status_code=503, detail="Piper executable is not installed.")
        if not self.model.exists():
            raise HTTPException(status_code=503, detail=f"Piper model is missing: {self.model.name}")

        try:
            with tempfile.TemporaryDirectory(prefix="eyay-piper-") as temp_dir:
                output = Path(temp_dir) / "speech.wav"
                completed = subprocess.run(
                    [str(self.binary), "--model", str(self.model), "--output_file", str(output)],
                    input=text,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    timeout=45.0,
                    check=False,
                )
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "Piper failed").strip()
                    raise RuntimeError(detail[-400:])
                audio = output.read_bytes()
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Piper TTS request failed: {exc.__class__.__name__}",
            ) from exc
        if not audio:
            raise HTTPException(status_code=503, detail="Piper returned no audio.")
        return audio


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
            # Kota/faturalama hataları (401/402/429) devre kesiciye girer: ücretsiz
            # Edge'e düşülür ve bir süre ücretli sağlayıcı hiç denenmez.
            if response.status_code in (401, 402, 429):
                raise TTSQuotaError(response.status_code)
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


class GoogleTranslateTTSProvider:
    """Keyless HTTP fallback for environments where Edge WebSocket TTS is
    rejected after a browser-version/token change.

    Google limits each request to a short phrase. Concatenated MPEG frames are
    accepted by the browser audio element and keep the voice route independent
    from trading state.
    """

    @staticmethod
    def _chunks(text: str) -> list[str]:
        words = text.split()
        chunks: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > GOOGLE_TTS_CHUNK_CHARS:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [text[:GOOGLE_TTS_CHUNK_CHARS]]

    def speak(self, text: str, voice: str | None = None) -> bytes:
        del voice  # The endpoint uses the Turkish language code below.
        audio = bytearray()
        try:
            with httpx.Client(
                timeout=15.0,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                for chunk in self._chunks(text):
                    query = urlencode(
                        {"ie": "UTF-8", "client": "tw-ob", "tl": "tr", "q": chunk}
                    )
                    response = client.get(f"{GOOGLE_TTS_ENDPOINT}?{query}")
                    if response.status_code >= 400:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    audio.extend(response.content)
        except (httpx.HTTPError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Google TTS request failed: {exc.__class__.__name__}",
            ) from exc
        if not audio:
            raise HTTPException(status_code=503, detail="Google TTS returned no audio.")
        return bytes(audio)


def get_tts_provider(name: str | None) -> TTSProvider:
    provider = (name or os.environ.get("TTS_PROVIDER") or "piper").strip().lower()
    if provider == "piper":
        return PiperTTSProvider()
    if provider == "elevenlabs":
        return ElevenLabsTTSProvider()
    if provider == "edge":
        return EdgeTTSProvider()
    raise HTTPException(status_code=503, detail=f"Unsupported TTS provider: {provider}")


def _fallback_audio(text: str) -> bytes:
    """Try free fallbacks in order; return 503 only when both fail."""
    last_error: HTTPException | None = None
    for provider in (EdgeTTSProvider(), GoogleTranslateTTSProvider()):
        try:
            return provider.speak(text=text, voice=None)
        except HTTPException as exc:
            last_error = exc
    raise last_error or HTTPException(status_code=503, detail="No TTS provider available.")


@router.post("/voice/speak")
def speak(req: VoiceSpeakRequest) -> Response:
    global _elevenlabs_skip_until
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")

    primary = req.provider or os.environ.get("TTS_PROVIDER") or "piper"
    primary_name = primary.strip().lower()
    # Kota devre kesici: kredi bitmişse (402) ücretli sağlayıcıyı hiç denemeden
    # doğrudan ücretsiz Edge'e git — her okumada +4 sn gecikme olmasın.
    if primary_name == "elevenlabs" and time.monotonic() < _elevenlabs_skip_until:
        return _as_response(_fallback_audio(text))
    try:
        audio = get_tts_provider(primary).speak(text=text, voice=req.voice)
    except TTSQuotaError:
        # Ücretli sağlayıcı kota/faturalama hatası → ücretsiz Edge'e düş +
        # sağlayıcıyı cooldown boyunca atla (kalıcı 402 fırtınasını önler).
        if primary_name != "edge":
            _elevenlabs_skip_until = time.monotonic() + _QUOTA_COOLDOWN_SEC
        audio = _fallback_audio(text)
    except HTTPException:
        # Diğer sağlayıcı hataları/kota dışı: ücretsiz Edge TTS'e otomatik düş —
        # kullanıcı tarayıcı sesine düşmeden önce hâlâ kaliteli bir ses alır.
        if primary_name == "piper":
            raise
        audio = _fallback_audio(text)
    return _as_response(audio)


def _as_response(audio: bytes) -> Response:
    media_type = "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"
    return Response(
        content=audio,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )
