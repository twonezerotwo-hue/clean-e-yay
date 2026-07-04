/**
 * POST /api/v1/chat/stream SSE istemcisi.
 *
 * EventSource yalnız GET desteklediği için fetch + ReadableStream ile elle
 * parse edilir. Event sözleşmesi (contracts/openapi.yaml postChatStream):
 *   status {stage, source} → meta {snapshot_id, evidence_used} → delta {text}*
 *   → done {tam ChatResponse}. "done" OTORİTEDİR: çağıran, biriken delta
 * metnini done.answer ile DEĞİŞTİRMELİDİR (kesinti/bulgu-düşürme düzeltmeleri
 * backend'de done.answer'a işlenir).
 *
 * Hata modeli: HTTP/ağ hatası (ya da body yokluğu) throw eder — çağıran ilk
 * delta gelmediyse non-stream POST /chat fallback'ine düşebilir. Akış sonunda
 * done gelmemişse null döner (kesinti sinyali).
 */
import type { ChatResponse, ChatTurn } from "@/types/generated/api";

import { API_BASE } from "./client";

export type ChatStreamStatus = {
  stage?: "context" | "grounded" | "llm" | string;
  source?: string | null;
};

export type ChatStreamMeta = {
  snapshot_id?: string;
  evidence_used?: string[];
  refused?: boolean;
};

export type ChatStreamHandlers = {
  onStatus?: (status: ChatStreamStatus) => void;
  onMeta?: (meta: ChatStreamMeta) => void;
  onDelta?: (text: string) => void;
  /** Backend'in beklenmedik hatayı taşıdığı `error` eventi (akış yine biter). */
  onErrorEvent?: (message: string) => void;
};

type SseFrame = { event: string; data: string };

/** Buffer'daki TAM frame'leri ayıklar; yarım frame buffer'da kalır. */
function drainFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const frames: SseFrame[] = [];
  let rest = buffer;
  for (;;) {
    const sep = rest.search(/\r?\n\r?\n/);
    if (sep < 0) break;
    const rawFrame = rest.slice(0, sep);
    rest = rest.slice(sep).replace(/^\r?\n\r?\n/, "");
    let event = "message";
    const dataLines: string[] = [];
    for (const line of rawFrame.split(/\r?\n/)) {
      if (line.startsWith(":")) continue; // keepalive/comment
      if (line.startsWith("event:")) {
        event = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).replace(/^ /, ""));
      }
    }
    if (dataLines.length) frames.push({ event, data: dataLines.join("\n") });
  }
  return { frames, rest };
}

function parseJson<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function streamChat(
  payload: { message: string; history?: ChatTurn[] },
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<ChatResponse | null> {
  const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: "POST",
    cache: "no-store",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(
      payload.history?.length
        ? { message: payload.message, history: payload.history }
        : { message: payload.message },
    ),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`API ${res.status} /api/v1/chat/stream`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: ChatResponse | null = null;

  const handleFrame = (frame: SseFrame) => {
    switch (frame.event) {
      case "status": {
        const status = parseJson<ChatStreamStatus>(frame.data);
        if (status) handlers.onStatus?.(status);
        break;
      }
      case "meta": {
        const meta = parseJson<ChatStreamMeta>(frame.data);
        if (meta) handlers.onMeta?.(meta);
        break;
      }
      case "delta": {
        const delta = parseJson<{ text?: string }>(frame.data);
        if (delta?.text) handlers.onDelta?.(delta.text);
        break;
      }
      case "done": {
        const response = parseJson<ChatResponse>(frame.data);
        if (response) done = response;
        break;
      }
      case "error": {
        const err = parseJson<{ message?: string }>(frame.data);
        handlers.onErrorEvent?.(err?.message ?? "stream error");
        break;
      }
      default:
        break; // bilinmeyen event: ileri uyumluluk için sessizce atla
    }
  };

  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const { frames, rest } = drainFrames(buffer);
    buffer = rest;
    for (const frame of frames) handleFrame(frame);
    if (done) break; // done otorite — sonrasını bekleme
  }
  return done;
}
