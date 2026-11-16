"""Local Windows Jarvis voice loop for E-yAy.

The dashboard uses the same VoiceStudio streaming ASR/TTS services. This
optional background process keeps a microphone session open when the browser
is closed, waits for ``Hey Atlas`` (or ``Atlas``), sends the remainder to the
existing E-yAy chat endpoint, and plays the local WAV response.

No broker or trading action is performed here; this process only forwards a
spoken question to the existing state-grounded chat route.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import winsound
from pathlib import Path
from typing import Any

import sounddevice as sd
import websockets

LOG = logging.getLogger("eyay.jarvis_voice")
SAMPLE_RATE = 16_000
BLOCKSIZE = 3_200  # 200 ms PCM frames
DEFAULT_API = "http://127.0.0.1:9000"
# Pin the local dictation model explicitly.  Relying only on VoiceStudio's
# persisted preference can route a native background client through the legacy
# ASR path, which then reports a misleading "model not installed" error even
# when the sherpa Whisper Tiny weights are present.
DEFAULT_VOICE_WS = (
    "ws://127.0.0.1:3900/v1/audio/transcriptions/stream"
    "?pcm=1&sr=16000&model=sherpa-whisper-tiny"
)
WAKE_WORDS = ("hey atlas", "atlas")
STATUS_PATH = Path("data/runtime/jarvis_voice_status.json")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip()


def _question_after_wake(text: str, wake_words: tuple[str, ...]) -> str | None:
    value = _fold(text)
    for wake in wake_words:
        match = re.search(rf"(?:^|\s){re.escape(_fold(wake))}(?:\s|[,.:;!?]|$)", value)
        if match:
            return text[match.end() :].strip(" ,.!?;:")
    return None


def _write_status(stage: str, detail: str | None = None) -> None:
    payload = {"stage": stage, "detail": detail}
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        LOG.debug("voice status yazılamadı", exc_info=True)


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_wav(url: str, text: str) -> bytes:
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "audio/wav"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        audio = response.read()
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError("E-yAy yerel ses servisi WAV döndürmedi")
    return audio


def _tray_icon(stop_event: threading.Event) -> None:
    """Best-effort tray icon; voice loop remains usable without pystray."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        LOG.warning("pystray/Pillow yok; tray ikonu olmadan çalışılıyor")
        return

    image = Image.new("RGB", (64, 64), "#07131b")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill="#00d7c2", outline="#8cf8ef", width=2)
    draw.text((24, 20), "A", fill="#07131b")

    def quit_agent(icon, _item):
        stop_event.set()
        icon.stop()

    def refresh_title(icon):
        while not stop_event.is_set():
            try:
                state = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
                stage = str(state.get("stage") or "idle")
                icon.title = f"E-yAy · Jarvis · {stage}"
            except (OSError, ValueError):
                pass
            time.sleep(1)

    icon = pystray.Icon(
        "eyay-jarvis",
        image,
        "E-yAy · Jarvis sesli asistan",
        menu=pystray.Menu(pystray.MenuItem("Kapat", quit_agent)),
    )
    threading.Thread(target=refresh_title, args=(icon,), daemon=True).start()
    icon.run()


async def _capture_session(
    ws_url: str, stop_event: threading.Event, wake_words: tuple[str, ...]
) -> str:
    """Capture one utterance; VoiceStudio owns VAD and returns the final text."""
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
    loop = asyncio.get_running_loop()

    def callback(indata, _frames, _time, status):
        if status:
            LOG.debug("mikrofon: %s", status)
        frame = bytes(indata)
        def enqueue() -> None:
            try:
                audio_queue.put_nowait(frame)
            except asyncio.QueueFull:
                LOG.debug("ses tamponu dolu; eski kare atlandı")
        loop.call_soon_threadsafe(enqueue)

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=1,
        dtype="int16",
        callback=callback,
    ):
        async with websockets.connect(ws_url, ping_interval=20, max_size=8 * 1024 * 1024) as websocket:
            _write_status("listening")
            sender = asyncio.create_task(_send_audio(websocket, audio_queue, stop_event))
            try:
                async for raw in websocket:
                    payload = json.loads(raw)
                    kind = payload.get("type")
                    if kind == "status":
                        _write_status(str(payload.get("stage") or "loading"))
                    elif kind == "partial":
                        partial = str(payload.get("text") or "")
                        _write_status("partial", partial)
                        if _question_after_wake(partial, wake_words) is not None:
                            # Barge-in: the first wake-word partial is enough
                            # to cut the currently playing local response.
                            winsound.PlaySound(None, winsound.SND_PURGE)
                    elif kind == "final":
                        return str(payload.get("text") or "").strip()
                    elif kind == "error":
                        raise RuntimeError(str(payload.get("message") or "ses tanıma hatası"))
            finally:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
    return ""


async def _send_audio(websocket, audio_queue: asyncio.Queue[bytes], stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        frame = await audio_queue.get()
        await websocket.send(frame)


async def run_agent(api_base: str, ws_url: str, wake_words: tuple[str, ...], once: bool) -> None:
    stop_event = threading.Event()
    threading.Thread(target=_tray_icon, args=(stop_event,), daemon=True).start()
    while not stop_event.is_set():
        try:
            _write_status("connecting")
            text = await _capture_session(ws_url, stop_event, wake_words)
            question = _question_after_wake(text, wake_words)
            if question:
                _write_status("thinking", question)
                result = await asyncio.to_thread(_post_json, f"{api_base}/api/v1/chat", {"message": question})
                answer = str(result.get("answer") or "").strip()
                if answer:
                    _write_status("speaking")
                    wav = await asyncio.to_thread(_post_wav, f"{api_base}/api/voice/speak", answer)
                    winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_ASYNC)
            _write_status("idle")
            if once:
                return
        except (OSError, RuntimeError, urllib.error.URLError, websockets.WebSocketException) as exc:
            _write_status("error", str(exc))
            LOG.warning("ses döngüsü: %s", exc)
            if once:
                raise
            await asyncio.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="E-yAy yerel Hey Atlas sesli asistanı")
    parser.add_argument("--api-base", default=DEFAULT_API)
    parser.add_argument("--voice-ws", default=DEFAULT_VOICE_WS)
    parser.add_argument("--wake-word", action="append", dest="wake_words")
    parser.add_argument("--once", action="store_true", help="tek bir cümle dinle ve çık")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    wake_words = tuple(args.wake_words or WAKE_WORDS)
    try:
        asyncio.run(run_agent(args.api_base.rstrip("/"), args.voice_ws, wake_words, args.once))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
