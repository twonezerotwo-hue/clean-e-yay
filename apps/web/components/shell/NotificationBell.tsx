"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api/client";
import {
  useAckAllNotifications,
  useAckNotification,
  useChat,
  useNotifications,
} from "@/lib/queries/hooks";
import type { ChatResponse, Notification, NotificationPriority } from "@/types/generated/api";

type BellMode = "feed" | "ask";
type AssistantMessage = { role: "user" | "agent"; text: string; meta?: ChatResponse };

type SpeechRecognitionResultEventLike = {
  results: ArrayLike<{ 0?: { transcript?: string } }>;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

const QUICK_PROMPTS = [
  "Son bildirimleri tek cümlede özetle.",
  "Şu an işlem açmaya en büyük engel ne?",
  "15 dakikalık fırsat var mı?",
  "RiskGate neyi bekliyor?",
];

function priorityColor(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "text-red-300 border-red-700/60";
    case "high":     return "text-orange-300 border-orange-700/60";
    case "medium":   return "text-amber-300 border-amber-700/60";
    case "low":      return "text-cyan-300 border-cyan-700/60";
  }
}

function priorityLabel(p: NotificationPriority): string {
  switch (p) {
    case "critical": return "kritik";
    case "high": return "yüksek";
    case "medium": return "orta";
    case "low": return "düşük";
  }
}

function relTime(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - t);
    const s = Math.round(diff / 1000);
    if (s < 60) return `${s}sn`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}dk`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}sa`;
    const d = Math.round(h / 24);
    return `${d}g`;
  } catch {
    return "?";
  }
}

function cleanForVoice(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .replace(/[•◆◇·]+/g, ".")
    .replace(/[_*`#<>[\](){}]/g, " ")
    .trim()
    .slice(0, 1200);
}

function latestNotificationBrief(items: Notification[], unread: number): string {
  if (!items.length) return "Bildirim yok. Sistem sessiz modda izliyor.";
  const latest = items[0];
  const prefix = unread > 0 ? `${unread} okunmamış bildirim var.` : "Okunmamış bildirim yok.";
  return `${prefix} Son kayıt: ${latest.title}. ${latest.body_short}`;
}

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function NotifRow({
  n,
  onAck,
  onAsk,
  onSpeak,
}: {
  n: Notification;
  onAck: (id: string) => void;
  onAsk: (n: Notification) => void;
  onSpeak: (n: Notification) => void;
}) {
  const cls = priorityColor(n.priority);
  return (
    <div className={`floating-notification-row border-l-2 ${cls} ${n.ack ? "opacity-50" : ""}`}>
      <div className="mb-0.5 flex items-baseline justify-between gap-2">
        <div className="truncate text-xs font-medium text-white/85">{n.title}</div>
        <div className="shrink-0 font-mono text-[10px] text-white/40">{relTime(n.ts)}</div>
      </div>
      <div className="text-[11px] leading-snug text-white/60">{n.body_short}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {!n.ack ? (
          <button type="button" onClick={() => onAck(n.id)} className="floating-notification-mini-btn">
            okundu
          </button>
        ) : null}
        <button type="button" onClick={() => onSpeak(n)} className="floating-notification-mini-btn">
          oku
        </button>
        <button type="button" onClick={() => onAsk(n)} className="floating-notification-mini-btn">
          sor
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ item }: { item: AssistantMessage }) {
  return (
    <div
      className={`floating-notification-chat-row ${
        item.role === "user"
          ? "floating-notification-chat-row--user"
          : item.meta?.refused
            ? "floating-notification-chat-row--blocked"
            : "floating-notification-chat-row--agent"
      }`}
    >
      <div className="floating-notification-chat-role">
        {item.role === "user" ? "Sen" : "E-yAy"}
      </div>
      <div>{item.text}</div>
      {item.role === "agent" && item.meta?.evidence_used?.length ? (
        <div className="mt-1 text-[10px] text-white/35">
          kanıt: {item.meta.evidence_used.slice(0, 3).join(" · ")}
        </div>
      ) : null}
    </div>
  );
}

export function NotificationBell() {
  const { data } = useNotifications();
  const chat = useChat();
  const ackMutation = useAckNotification();
  const ackAllMutation = useAckAllNotifications();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<BellMode>("feed");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [micReady, setMicReady] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const seenIds = useRef<Set<string>>(new Set());
  const initialized = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const speechRunRef = useRef(0);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const items: Notification[] = data?.notifications ?? [];
  const unread = data?.unread_count ?? 0;
  const assistantBrief = useMemo(() => latestNotificationBrief(items, unread), [items, unread]);

  const clearAudioPlayback = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      window.URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }, []);

  const speakWithBrowserFallback = useCallback((text: string) => {
    if (!voiceEnabled || typeof window === "undefined" || !("speechSynthesis" in window)) {
      return false;
    }
    const cleanText = cleanForVoice(text);
    if (!cleanText) return false;

    clearAudioPlayback();
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = "tr-TR";
    utterance.rate = 1.0;
    utterance.pitch = 1.03;
    const voices = window.speechSynthesis.getVoices();
    const isNatural = (v: SpeechSynthesisVoice) =>
      /natural|neural|online|google|premium|wavenet|siri/i.test(v.name);
    const isTr = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().startsWith("tr");
    const isEn = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().startsWith("en");
    utterance.voice =
      voices.find((v) => isTr(v) && isNatural(v)) ??
      voices.find(isTr) ??
      voices.find((v) => isEn(v) && isNatural(v)) ??
      voices.find(isEn) ??
      null;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    return true;
  }, [clearAudioPlayback, voiceEnabled]);

  const speak = useCallback(async (text: string) => {
    const cleanText = cleanForVoice(text);
    if (!voiceEnabled || !cleanText || typeof window === "undefined") return false;

    const runId = speechRunRef.current + 1;
    speechRunRef.current = runId;
    setVoiceError(null);
    setVoiceLoading(true);
    setSpeaking(false);
    clearAudioPlayback();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();

    try {
      const audioBlob = await api.voiceSpeak({ text: cleanText });
      if (speechRunRef.current !== runId) return false;
      const audioUrl = window.URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audioUrlRef.current = audioUrl;
      audio.onended = () => {
        if (speechRunRef.current !== runId) return;
        setSpeaking(false);
        clearAudioPlayback();
      };
      audio.onerror = () => {
        if (speechRunRef.current !== runId) return;
        setSpeaking(false);
        setVoiceError("Ses üretilemedi.");
        clearAudioPlayback();
      };
      setVoiceLoading(false);
      setSpeaking(true);
      await audio.play();
      return true;
    } catch {
      if (speechRunRef.current !== runId) return false;
      setVoiceLoading(false);
      setSpeaking(false);
      clearAudioPlayback();
      const fallbackSpoke = speakWithBrowserFallback(cleanText);
      setVoiceError(
        fallbackSpoke
          ? "Kaliteli ses üretilemedi; tarayıcı sesi kullanılıyor."
          : "Ses üretilemedi.",
      );
      return fallbackSpoke;
    }
  }, [clearAudioPlayback, speakWithBrowserFallback, voiceEnabled]);

  const stopSpeaking = useCallback(() => {
    speechRunRef.current += 1;
    clearAudioPlayback();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
    setVoiceLoading(false);
  }, [clearAudioPlayback]);

  const send = useCallback((message: string) => {
    const text = message.trim();
    if (!text || chat.isPending) return;
    setOpen(true);
    setMode("ask");
    setMessages((xs) => [...xs, { role: "user", text }]);
    setInput("");
    chat.mutate(text, {
      onSuccess: (res) => {
        setMessages((xs) => [...xs, { role: "agent", text: res.answer, meta: res }]);
        void speak(res.answer);
      },
      onError: () => {
        const fallback = "Şu an chat yanıtı alınamadı. Bağlantı gelince aynı soruyu tekrar cevaplayabilirim.";
        setMessages((xs) => [...xs, { role: "agent", text: fallback }]);
        void speak(fallback);
      },
    });
  }, [chat, speak]);

  const startListening = useCallback(() => {
    if (chat.isPending || listening) return;
    const Recognition = getSpeechRecognition();
    if (!Recognition) {
      setVoiceError("Mikrofon bu tarayıcıda hazır değil.");
      return;
    }
    recognitionRef.current?.stop();
    const recognition = new Recognition();
    recognition.lang = "tr-TR";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = Array.from({ length: event.results.length }, (_, index) =>
        event.results[index]?.[0]?.transcript ?? "",
      ).join(" ").trim();
      if (transcript) send(transcript);
    };
    recognition.onerror = () => {
      setListening(false);
      setVoiceError("Mikrofon dinlemesi tamamlanamadı.");
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }, [chat.isPending, listening, send]);

  useEffect(() => {
    setMicReady(Boolean(getSpeechRecognition()));
    return () => {
      speechRunRef.current += 1;
      recognitionRef.current?.stop();
      clearAudioPlayback();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, [clearAudioPlayback]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  useEffect(() => {
    const notifications = data?.notifications ?? [];
    if (!initialized.current) {
      notifications.forEach((n) => seenIds.current.add(n.id));
      initialized.current = true;
      return;
    }
    const fresh = notifications.filter((n) => !n.ack && !seenIds.current.has(n.id));
    if (!fresh.length) return;
    fresh.forEach((n) => seenIds.current.add(n.id));
    const first = fresh[0];
    void speak(`Yeni ${priorityLabel(first.priority)} bildirim: ${first.title}. ${first.body_short}`);
  }, [data, speak]);

  const askAboutNotification = (n: Notification) => {
    send(`Bu bildirimi açıkla: ${n.title}. ${n.body_long || n.body_short}`);
  };

  const speakNotification = (n: Notification) => {
    void speak(`${n.title}. ${n.body_long || n.body_short}`);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    send(input);
  };

  return (
    <div
      className="floating-notification-dock"
      data-open={open ? "true" : "false"}
      data-speaking={speaking || voiceLoading ? "true" : "false"}
      data-unread={unread > 0 ? "true" : "false"}
      ref={ref}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="floating-notification-button"
        aria-label="E-yAy bildirim ve konuşma asistanı"
      >
        <img
          src="/icons/eyay-notification-bell.png"
          alt=""
          className="floating-notification-image"
          draggable={false}
        />
        <span className="floating-notification-status-dot" aria-hidden />
        {unread > 0 ? (
          <span className="floating-notification-badge">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="floating-notification-panel">
          <div className="floating-notification-head">
            <div>
              <div className="floating-notification-kicker">E-yAy Sentinel</div>
              <div className="text-[11px] text-white/60">
                {unread} okunmamış · {voiceLoading ? "ses hazırlanıyor" : speaking ? "konuşuyor" : "hazır"}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setVoiceEnabled((value) => !value)}
                className={`floating-notification-chip ${voiceEnabled ? "is-active" : ""}`}
              >
                {voiceEnabled ? "Ses açık" : "Ses kapalı"}
              </button>
              <button
                type="button"
                onClick={speaking || voiceLoading ? stopSpeaking : () => void speak(assistantBrief)}
                className="floating-notification-chip"
              >
                {speaking || voiceLoading ? "Durdur" : "Oku"}
              </button>
            </div>
          </div>

          <div className="floating-notification-oracle">
            <div className="floating-notification-oracle-pulse" aria-hidden />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-200/60">
                canlı özet
              </div>
              <p>{assistantBrief}</p>
              {voiceError ? <div className="floating-notification-voice-error">{voiceError}</div> : null}
            </div>
          </div>

          <div className="floating-notification-tabs">
            <button
              type="button"
              onClick={() => setMode("feed")}
              className={mode === "feed" ? "is-active" : ""}
            >
              Akış
            </button>
            <button
              type="button"
              onClick={() => setMode("ask")}
              className={mode === "ask" ? "is-active" : ""}
            >
              E-yAy'a sor
            </button>
            {unread > 0 ? (
              <button
                type="button"
                onClick={() => ackAllMutation.mutate()}
                className="ml-auto"
              >
                hepsi okundu
              </button>
            ) : null}
          </div>

          {mode === "feed" ? (
            <div className="floating-notification-feed">
              {items.length === 0 ? (
                <div className="px-4 py-6 text-center text-xs italic text-white/40">
                  Henüz bildirim yok.
                </div>
              ) : (
                items.map((n) => (
                  <NotifRow
                    key={n.id}
                    n={n}
                    onAck={(id) => ackMutation.mutate(id)}
                    onAsk={askAboutNotification}
                    onSpeak={speakNotification}
                  />
                ))
              )}
            </div>
          ) : (
            <div className="floating-notification-chat">
              <div className="floating-notification-chat-log">
                {messages.length === 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs leading-relaxed text-white/55">
                      Bildirimleri, risk kapısını veya 15 dakikalık fırsatı sor. Cevabı mevcut backend state'inden alır; emir üretmez.
                    </div>
                    {QUICK_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => send(prompt)}
                        className="floating-notification-prompt"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                ) : (
                  messages.map((item, index) => <ChatBubble key={`${item.role}-${index}`} item={item} />)
                )}
                {chat.isPending ? (
                  <div className="floating-notification-chat-row floating-notification-chat-row--agent">
                    <div className="floating-notification-chat-role">E-yAy</div>
                    Cevap hazırlanıyor...
                  </div>
                ) : null}
              </div>
              <form onSubmit={handleSubmit} className="floating-notification-input">
                <button
                  type="button"
                  onClick={startListening}
                  disabled={!micReady || listening || chat.isPending}
                  aria-label="Sesli soru sor"
                >
                  {listening ? "..." : "Mic"}
                </button>
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Soru yaz..."
                  maxLength={2000}
                />
                <button type="submit" disabled={chat.isPending || !input.trim()}>
                  Sor
                </button>
              </form>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
