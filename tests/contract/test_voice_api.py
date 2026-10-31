"""Contract tests for E-YAY's single local VoiceStudio provider."""
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routers import voice as voice_router


FAKE_WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"data"


def test_voice_speak_rejects_empty_text() -> None:
    client = TestClient(create_app())
    response = client.post("/api/voice/speak", json={"text": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "text is required."


def test_voice_speak_uses_voicestudio_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        voice_router.VoiceStudioTTSProvider,
        "speak",
        lambda self, text, voice=None: FAKE_WAV,
    )
    response = TestClient(create_app()).post("/api/voice/speak", json={"text": "Merhaba."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-voice-provider"] == "voicestudio-local"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == FAKE_WAV


def test_legacy_provider_cannot_switch_engine(monkeypatch) -> None:
    calls = []

    def fake_speak(self, text: str, voice: str | None = None) -> bytes:
        calls.append((text, voice))
        return FAKE_WAV

    monkeypatch.setattr(voice_router.VoiceStudioTTSProvider, "speak", fake_speak)
    response = TestClient(create_app()).post(
        "/api/voice/speak",
        json={"text": "Yerel ses.", "provider": "elevenlabs", "voice": "remote"},
    )
    assert response.status_code == 200
    assert response.headers["x-voice-provider"] == "voicestudio-local"
    assert calls == [("Yerel ses.", "remote")]


def test_voice_speak_normalizes_turkish_combining_characters(monkeypatch) -> None:
    calls = []

    def fake_speak(self, text: str, voice: str | None = None) -> bytes:
        calls.append(text)
        return FAKE_WAV

    monkeypatch.setattr(voice_router.VoiceStudioTTSProvider, "speak", fake_speak)
    TestClient(create_app()).post(
        "/api/voice/speak",
        json={"text": "İşlem i\u0307zleniyor.  Gümüş."},
    )
    assert calls == ["İşlem izleniyor. Gümüş."]


def test_voicestudio_posts_configured_profile_utf8(monkeypatch) -> None:
    observed = {}

    class FakeConnection:
        def __init__(self, host, port, timeout):
            observed.update(host=host, port=port, timeout=timeout)

        def request(self, method, path, body=None, headers=None):
            observed.update(method=method, path=path, payload=json.loads(body), headers=headers)

        def getresponse(self):
            class Result:
                status = 200

                def read(self, size):
                    return FAKE_WAV

            return Result()

        def close(self):
            observed["closed"] = True

    monkeypatch.setattr(voice_router.http.client, "HTTPConnection", FakeConnection)
    monkeypatch.setenv("VOICESTUDIO_API_URL", "http://127.0.0.1:3900/v1/audio/speech")
    monkeypatch.setenv("VOICESTUDIO_VOICE", "türkçe voice 1")
    monkeypatch.setenv("VOICESTUDIO_SPEED", "0.85")
    provider = voice_router.VoiceStudioTTSProvider()
    assert provider.speak("Sıkıntı şu: gümüş, güven ve ölçüm.", "ignored") == FAKE_WAV
    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 3900
    assert observed["method"] == "POST"
    assert observed["path"] == "/v1/audio/speech"
    assert observed["payload"] == {
        "model": "tts-1",
        "voice": "türkçe voice 1",
        "input": "Sıkıntı şu: gümüş, güven ve ölçüm.",
        "speed": 0.85,
        "response_format": "wav",
    }
    assert observed["closed"]


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:3900/v1/audio/speech",
        "http://example.com/v1/audio/speech",
        "http://127.0.0.1:3900/other",
        "http://127.0.0.1:3900/v1/audio/speech?next=1",
        "http://name:pass@127.0.0.1:3900/v1/audio/speech",
    ],
)
def test_voicestudio_rejects_nonlocal_endpoint(monkeypatch, url) -> None:
    monkeypatch.setenv("VOICESTUDIO_API_URL", url)
    with pytest.raises(HTTPException) as exc:
        voice_router.VoiceStudioTTSProvider()
    assert exc.value.status_code == 503


def test_voicestudio_api_unavailable_returns_503(monkeypatch) -> None:
    class ConnectionUnavailable:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise ConnectionRefusedError("offline")

        def close(self):
            pass

    monkeypatch.setattr(voice_router.http.client, "HTTPConnection", ConnectionUnavailable)
    with pytest.raises(HTTPException) as exc:
        voice_router.VoiceStudioTTSProvider().speak("Merhaba")
    assert exc.value.status_code == 503


def test_voicestudio_does_not_fallback_to_other_tts(monkeypatch) -> None:
    def unavailable(self, text: str, voice: str | None = None) -> bytes:
        raise HTTPException(status_code=503, detail="VoiceStudio local TTS is unavailable.")

    monkeypatch.setattr(voice_router.VoiceStudioTTSProvider, "speak", unavailable)
    response = TestClient(create_app()).post("/api/voice/speak", json={"text": "Merhaba."})
    assert response.status_code == 503
