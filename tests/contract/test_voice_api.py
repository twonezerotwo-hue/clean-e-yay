from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routers import voice as voice_router


def test_voice_speak_rejects_empty_text() -> None:
    client = TestClient(create_app())
    response = client.post("/api/voice/speak", json={"text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "text is required."


def test_voice_speak_uses_local_piper_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        voice_router.PiperTTSProvider,
        "speak",
        lambda self, text, voice=None: b"RIFF" + b"fake-wav",
    )
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "Merhaba."})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-voice-provider"] == "piper-local"
    assert response.content == b"RIFFfake-wav"


def test_voice_speak_ignores_legacy_provider_selection(monkeypatch) -> None:
    calls: list[str] = []

    def _piper(self, text: str, voice: str | None = None) -> bytes:
        calls.append(text)
        return b"RIFFpiper-wav"

    monkeypatch.setattr(voice_router.PiperTTSProvider, "speak", _piper)
    client = TestClient(create_app())

    response = client.post(
        "/api/voice/speak",
        json={"text": "Yerel ses.", "provider": "elevenlabs", "voice": "remote"},
    )

    assert response.status_code == 200
    assert response.content == b"RIFFpiper-wav"
    assert calls == ["Yerel ses."]


def test_voice_speak_normalizes_turkish_combining_characters(monkeypatch) -> None:
    calls: list[str] = []

    def _piper(self, text: str, voice: str | None = None) -> bytes:
        calls.append(text)
        return b"RIFFpiper-wav"

    monkeypatch.setattr(voice_router.PiperTTSProvider, "speak", _piper)
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "İşlem i\u0307zleniyor.  Gümüş."})

    assert response.status_code == 200
    assert calls == ["İşlem izleniyor. Gümüş."]


def test_voice_speak_does_not_fallback_when_piper_is_unavailable(monkeypatch) -> None:
    def _piper_boom(self, text: str, voice: str | None = None) -> bytes:
        raise HTTPException(status_code=503, detail="Piper executable is not installed.")

    monkeypatch.setattr(voice_router.PiperTTSProvider, "speak", _piper_boom)
    client = TestClient(create_app())

    response = client.post("/api/voice/speak", json={"text": "Piper kontrol."})

    assert response.status_code == 503
    assert response.json()["detail"] == "Piper executable is not installed."


def test_piper_reads_utf8_file_for_turkish_characters(monkeypatch, tmp_path) -> None:
    """Windows stdin code pages must not corrupt dotless ı or other Turkish letters."""
    provider = object.__new__(voice_router.PiperTTSProvider)
    provider.binary = tmp_path / "piper.exe"
    provider.model = tmp_path / "tr_TR-dfki-medium.onnx"
    provider.use_cuda = False
    provider.runtime_env = {}
    provider.binary.touch()
    provider.model.touch()
    seen: dict[str, str] = {}

    def _run(command, **kwargs):
        input_path = Path(command[command.index("--input_file") + 1])
        seen["text"] = input_path.read_text(encoding="utf-8")
        output = Path(command[command.index("--output_file") + 1])
        output.write_bytes(b"RIFFfake-wav")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr(voice_router.subprocess, "run", _run)

    audio = provider.speak("Sıkıntı şu: işlem açılmıyor; gümüş, güven ve ölçüm.")

    assert audio == b"RIFFfake-wav"
    assert seen["text"] == "Sıkıntı şu: işlem açılmıyor; gümüş, güven ve ölçüm.\n"
