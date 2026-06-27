from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routers import voice as voice_router


def test_voice_speak_rejects_empty_text() -> None:
    client = TestClient(create_app())
    response = client.post("/api/voice/speak", json={"text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "text is required."


def test_voice_speak_falls_back_to_edge_when_primary_unconfigured(monkeypatch) -> None:
    """ElevenLabs key missing → speak() no longer hard-fails; it falls back to
    the free Edge TTS provider so the caller still gets quality audio (see
    voice.py's speak() comment). Edge itself is monkeypatched — no real
    network call / edge_tts install needed for this test."""
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(
        voice_router.EdgeTTSProvider,
        "speak",
        lambda self, text, voice=None: b"fake-mp3-bytes",
    )
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "Merhaba."})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"fake-mp3-bytes"


def test_voice_speak_503_when_both_providers_fail(monkeypatch) -> None:
    """Primary (ElevenLabs, key missing) AND the Edge fallback both fail →
    the request genuinely has no audio to return, so 503 is correct."""
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    def _edge_boom(self, text: str, voice: str | None = None) -> bytes:
        raise HTTPException(status_code=503, detail="Edge TTS request failed: Boom")

    monkeypatch.setattr(voice_router.EdgeTTSProvider, "speak", _edge_boom)
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "Merhaba."})

    assert response.status_code == 503
