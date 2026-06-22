from fastapi.testclient import TestClient

from apps.api.main import create_app


def test_voice_speak_rejects_empty_text() -> None:
    client = TestClient(create_app())
    response = client.post("/api/voice/speak", json={"text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "text is required."


def test_voice_speak_requires_provider_key(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "Merhaba."})

    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]
