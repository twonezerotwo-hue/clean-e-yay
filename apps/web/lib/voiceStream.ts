export type LocalVoiceStreamCallbacks = {
  onPartial: (text: string) => void;
  onFinal: (text: string) => void;
  onStatus?: (stage: string) => void;
  onError?: (message: string) => void;
};

export type LocalVoiceStreamHandle = {
  stop: () => void;
};

const DEFAULT_WS_URL = "ws://127.0.0.1:3900/v1/audio/transcriptions/stream";
const SAMPLE_RATE = 16_000;
const WS_OPEN = 1;

function streamUrl(): string {
  const configured = process.env.NEXT_PUBLIC_VOICESTUDIO_WS_URL?.trim();
  const base = configured || DEFAULT_WS_URL;
  const separator = base.includes("?") ? "&" : "?";
  // VoiceStudio's saved dictation preference selects the installed model
  // (tiny/large) and keeps the dashboard independent of model filenames.
  return `${base}${separator}pcm=1&sr=${SAMPLE_RATE}`;
}

function resampleToPcm16(input: Float32Array, inputRate: number): ArrayBuffer {
  if (!input.length) return new ArrayBuffer(0);
  const outputLength = Math.max(1, Math.round(input.length * SAMPLE_RATE / inputRate));
  const output = new Int16Array(outputLength);
  const ratio = inputRate / SAMPLE_RATE;
  for (let i = 0; i < outputLength; i += 1) {
    const source = Math.min(input.length - 1, Math.floor(i * ratio));
    const sample = Math.max(-1, Math.min(1, input[source] ?? 0));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output.buffer;
}

function stopTracks(stream: MediaStream | null): void {
  for (const track of stream?.getTracks() ?? []) track.stop();
}

/**
 * Local VoiceStudio streaming dictation.
 *
 * VoiceStudio owns VAD/end-of-turn detection. E-yAy only transports 16-bit
 * mono PCM and consumes partial/final events, so a text stop does not race the
 * final transcription. Returns null when the local engine is unavailable;
 * callers can then use the existing browser-recognition fallback.
 */
export async function startLocalVoiceStream(
  callbacks: LocalVoiceStreamCallbacks,
): Promise<LocalVoiceStreamHandle | null> {
  if (
    typeof window === "undefined" ||
    typeof WebSocket === "undefined" ||
    !navigator.mediaDevices?.getUserMedia ||
    typeof AudioContext === "undefined"
  ) {
    return null;
  }

  let media: MediaStream;
  try {
    media = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch {
    return null;
  }

  let audioContext: AudioContext;
  try {
    audioContext = new AudioContext();
  } catch {
    stopTracks(media);
    return null;
  }

  const websocket = new WebSocket(streamUrl());
  websocket.binaryType = "arraybuffer";
  let processor: ScriptProcessorNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let stopped = false;
  let opened = false;
  let finished = false;
  let stopTimer: number | null = null;

  const cleanup = () => {
    if (stopTimer !== null) window.clearTimeout(stopTimer);
    stopTimer = null;
    processor?.disconnect();
    source?.disconnect();
    processor = null;
    source = null;
    stopTracks(media);
    void audioContext.close().catch(() => {});
  };

  const finish = (text: string) => {
    if (finished) return;
    finished = true;
    cleanup();
    if (text.trim()) callbacks.onFinal(text.trim());
  };

  const handle: LocalVoiceStreamHandle = {
    stop: () => {
      if (stopped) return;
      stopped = true;
      cleanup();
      if (websocket.readyState === WS_OPEN) {
        websocket.send("EOF");
        stopTimer = window.setTimeout(() => {
          if (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING) {
            websocket.close();
          }
        }, 5000);
      } else if (!finished) {
        websocket.close();
      }
    },
  };

  websocket.onmessage = (event) => {
    let payload: { type?: string; text?: string; stage?: string; message?: string };
    try {
      payload = JSON.parse(String(event.data)) as typeof payload;
    } catch {
      return;
    }
    if (payload.type === "partial" && payload.text) callbacks.onPartial(payload.text);
    else if (payload.type === "final") finish(payload.text ?? "");
    else if (payload.type === "status" && payload.stage) callbacks.onStatus?.(payload.stage);
    else if (payload.type === "error") callbacks.onError?.(payload.message || "Yerel ses tanıma başarısız.");
  };

  websocket.onerror = () => {
    if (!opened) {
      cleanup();
      websocket.close();
    } else {
      callbacks.onError?.("Yerel ses akışı kullanılamıyor.");
    }
  };

  websocket.onclose = () => {
    cleanup();
    if (!finished && !stopped) callbacks.onError?.("Yerel ses akışı kapandı.");
  };

  websocket.onopen = () => {
    opened = true;
    callbacks.onStatus?.("ready");
    try {
      source = audioContext.createMediaStreamSource(media);
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      const silentSink = audioContext.createGain();
      silentSink.gain.value = 0;
      processor.onaudioprocess = (event) => {
        if (stopped || websocket.readyState !== WS_OPEN) return;
        const pcm = resampleToPcm16(event.inputBuffer.getChannelData(0), audioContext.sampleRate);
        if (pcm.byteLength) websocket.send(pcm);
      };
      source.connect(processor);
      processor.connect(silentSink);
      silentSink.connect(audioContext.destination);
    } catch {
      callbacks.onError?.("Mikrofon akışı başlatılamadı.");
      handle.stop();
    }
  };

  // Give the loopback service a short handshake window before falling back to
  // the browser recognizer. This avoids a dead local TTS/ASR process blocking PTT.
  await new Promise<void>((resolve) => window.setTimeout(resolve, 900));
  if (!opened) {
    handle.stop();
    return null;
  }
  return handle;
}
