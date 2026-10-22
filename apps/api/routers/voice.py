"""POST /api/voice/speak — the application's local Piper voice route.

All spoken output (briefings, chat replies and notification reads) uses the
same locally installed Piper model. The route deliberately has no cloud or
browser TTS fallback: a missing Piper installation is reported explicitly so
that one voice cannot silently turn into another.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["voice"])

MAX_TTS_CHARS = 4000
DEFAULT_PIPER_MODEL = "tr_TR-dfki-medium.onnx"


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def normalize_voice_text(value: str) -> str:
    """Piper'a UTF-8 ve Türkçe NFC metin gönder.

    Python'da büyük ``İ`` bazı ara dönüşümlerde ``i`` + birleşik nokta olarak
    kalabiliyor. Piper bunu ayrı bir sembol gibi telaffuz edebildiği için ses
    girişini tek biçime indiriyor; karar/ekran metni değiştirilmez.
    """
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("i\u0307", "i")
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class VoiceSpeakRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_CHARS)
    # Kept for old clients. They are intentionally ignored; Piper is the only
    # supported output provider and voice is encoded in the local model.
    voice: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=32)


class TTSProvider(Protocol):
    def speak(self, text: str, voice: str | None = None) -> bytes:
        """Return playable WAV bytes for text."""


class PiperTTSProvider:
    """Local Turkish Piper voice, invoked as an isolated executable."""

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[3]
        configured_model = os.environ.get("PIPER_MODEL", "").strip()
        self.model = (
            Path(configured_model)
            if configured_model
            else root / "data" / "models" / "piper" / DEFAULT_PIPER_MODEL
        )
        if not self.model.is_absolute():
            self.model = root / self.model

        configured_bin = os.environ.get("PIPER_BIN", "").strip()
        configured_path = Path(configured_bin) if configured_bin else None
        if configured_path is not None and not configured_path.is_absolute():
            configured_path = root / configured_path
        # Keep the voice runtime isolated from the application venv.  This lets
        # Piper/ONNX upgrades be rolled back without touching the API, workers,
        # or decision packages.  The application venv remains the safe fallback
        # for older clones that have not run the voice bootstrap yet.
        isolated_candidates = [
            root / ".voice-venv" / "Scripts" / "piper.exe",
            root / ".voice-venv" / "bin" / "piper",
        ]
        candidates = [
            configured_path,
            *isolated_candidates,
            Path(sys.executable).with_name("piper.exe"),
        ]
        self.binary = next(
            (candidate for candidate in candidates if candidate and candidate.exists()),
            Path(shutil.which("piper") or "piper"),
        )
        self.use_cuda = _env_true("PIPER_USE_CUDA", default=False) and self._cuda_runtime_available(root)
        self.runtime_env = self._runtime_env(root)

    @staticmethod
    def _cuda_runtime_available(root: Path) -> bool:
        voice_site = root / ".voice-venv" / "Lib" / "site-packages"
        return all(
            path.exists()
            for path in (
                voice_site / "nvidia" / "cu13" / "bin" / "x86_64",
                voice_site / "nvidia" / "cudnn" / "bin",
            )
        )

    def _runtime_env(self, root: Path) -> dict[str, str]:
        """Return a child environment with optional bundled CUDA DLLs visible."""
        env = os.environ.copy()
        if not self.use_cuda:
            return env
        voice_site = root / ".voice-venv" / "Lib" / "site-packages"
        cuda_dirs = (
            voice_site / "nvidia" / "cu13" / "bin" / "x86_64",
            voice_site / "nvidia" / "cudnn" / "bin",
        )
        existing = [str(path) for path in cuda_dirs if path.exists()]
        if existing:
            env["PATH"] = os.pathsep.join([*existing, env.get("PATH", "")])
        return env

    def speak(self, text: str, voice: str | None = None) -> bytes:
        del voice  # The Turkish speaker is part of the Piper model.
        if not self.binary.exists() and self.binary.name != "piper":
            raise HTTPException(status_code=503, detail="Piper executable is not installed.")
        if not self.model.exists():
            raise HTTPException(status_code=503, detail=f"Piper model is missing: {self.model.name}")

        try:
            with tempfile.TemporaryDirectory(prefix="eyay-piper-") as temp_dir:
                # On Windows, Piper's ``sys.stdin`` inherits the console code
                # page even when the parent process writes UTF-8 bytes. That
                # turns Turkish letters (especially dotless ``ı``) into
                # surrogate characters before espeak sees them. Piper's own
                # input-file path explicitly opens UTF-8, so use it for every
                # request instead of piping text through stdin.
                input_file = Path(temp_dir) / "speech.txt"
                input_file.write_text(text + "\n", encoding="utf-8", newline="")
                output = Path(temp_dir) / "speech.wav"
                command = [
                    str(self.binary),
                    "--model",
                    str(self.model),
                    "--input_file",
                    str(input_file),
                    "--output_file",
                    str(output),
                ]
                if self.use_cuda:
                    command.append("--cuda")
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    env=self.runtime_env,
                    timeout=45.0,
                    check=False,
                )
                # CUDA is an optional accelerator. A machine can retain the
                # flag in .env after a driver/runtime change; retry once on
                # the known ONNX provider-load failure instead of breaking
                # every voice request.
                cuda_failed = self.use_cuda and any(
                    marker in (completed.stderr or "")
                    for marker in ("Error loading", "Failed to create CUDAExecutionProvider")
                )
                if (completed.returncode != 0 or cuda_failed) and self.use_cuda:
                    output.unlink(missing_ok=True)
                    completed = subprocess.run(
                        [
                            str(self.binary),
                            "--model",
                            str(self.model),
                            "--input_file",
                            str(input_file),
                            "--output_file",
                            str(output),
                        ],
                        capture_output=True,
                        env=os.environ.copy(),
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


def get_tts_provider(name: str | None = None) -> TTSProvider:
    """Return the one and only voice provider used by the application.

    ``name`` is retained for request compatibility, but deliberately ignored:
    a request must never route audio to a cloud or browser-specific provider.
    """
    del name
    return PiperTTSProvider()


@router.post("/voice/speak")
def speak(req: VoiceSpeakRequest) -> Response:
    text = normalize_voice_text(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    # ``provider`` and ``voice`` are accepted for old clients but do not alter
    # routing. Every output must be produced by the local Piper installation.
    audio = get_tts_provider().speak(text=text, voice=req.voice)
    return _as_response(audio)


def _as_response(audio: bytes) -> Response:
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Voice-Provider": "piper-local"},
    )
