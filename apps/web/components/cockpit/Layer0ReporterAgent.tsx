"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useAgentBriefing, useChat } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";
import type { ChatResponse } from "@/types/generated/api";

type ReporterMessage = {
  role: "user" | "agent";
  text: string;
  meta?: ChatResponse;
};

type SpeechRecognitionResultLike = {
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  results: {
    [index: number]: SpeechRecognitionResultLike;
    length: number;
  };
};

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const QUICK_PROMPTS = [
  "15 dakikalik firsat var mi?",
  "Son 1 saat haberlerini ozetle.",
  "Neden islem yok?",
  "Isleme en yakin aday hangisi?",
  "Risk tarafinda beni ne engelliyor?",
  "Bana 30 saniyelik piyasa brifingi ver.",
];

const CATEGORY_LABEL: Record<string, string> = {
  market: "Piyasa",
  agent: "Agent",
  risk: "Risk",
  events: "Olay",
  news: "Haber",
  providers: "Saglayici",
  alerts: "Bildirim",
  system: "Sistem",
};

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scopedWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return scopedWindow.SpeechRecognition ?? scopedWindow.webkitSpeechRecognition ?? null;
}

function cleanForVoice(text: string) {
  return text
    .replace(/\s+/g, " ")
    .replace(/[•·]/g, ".")
    .trim()
    .slice(0, 900);
}

export function Layer0ReporterAgent() {
  const briefing = useAgentBriefing();
  const chat = useChat();
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [messages, setMessages] = useState<ReporterMessage[]>([]);
  const [input, setInput] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [listening, setListening] = useState(false);
  const [speechReady, setSpeechReady] = useState(false);
  const [micReady, setMicReady] = useState(false);

  useEffect(() => {
    setSpeechReady(typeof window !== "undefined" && "speechSynthesis" in window);
    setMicReady(Boolean(getSpeechRecognition()));
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      recognitionRef.current?.stop();
    };
  }, []);

  const briefingText = useMemo(() => {
    const headlines = briefing.data?.headlines ?? [];
    if (!headlines.length) return "Briefing bekleniyor. Bir sonraki veri cycle'i okunuyor.";
    return headlines
      .slice(0, 4)
      .map((item) => `${CATEGORY_LABEL[item.category] ?? item.category}: ${item.title}`)
      .join(". ");
  }, [briefing.data?.headlines]);

  const latestAgentText = useMemo(() => {
    const last = [...messages].reverse().find((item) => item.role === "agent");
    return last?.text ?? briefingText;
  }, [briefingText, messages]);

  const speak = (text: string) => {
    if (!voiceEnabled || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanForVoice(text));
    utterance.lang = "tr-TR";
    utterance.rate = 0.96;
    utterance.pitch = 0.92;
    const voices = window.speechSynthesis.getVoices();
    utterance.voice =
      voices.find((voice) => voice.lang.toLowerCase().startsWith("tr")) ??
      voices.find((voice) => voice.lang.toLowerCase().startsWith("en")) ??
      null;
    window.speechSynthesis.speak(utterance);
  };

  const send = (message: string) => {
    const text = message.trim();
    if (!text || chat.isPending) return;
    setMessages((items) => [...items, { role: "user", text }]);
    setInput("");
    chat.mutate(text, {
      onSuccess: (response) => {
        setMessages((items) => [
          ...items,
          { role: "agent", text: response.answer, meta: response },
        ]);
        speak(response.answer);
      },
      onError: () => {
        const fallback =
          "API chat yaniti alinamadi. Katman 0 sadece mevcut backend verisine bagli calisir; baglanti gelince soruyu yeniden cevaplayabilirim.";
        setMessages((items) => [...items, { role: "agent", text: fallback }]);
        speak(fallback);
      },
    });
  };

  const startListening = () => {
    if (listening || chat.isPending) return;
    const Recognition = getSpeechRecognition();
    if (!Recognition) return;
    const recognition = new Recognition();
    recognition.lang = "tr-TR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript ?? "";
      setListening(false);
      if (transcript.trim()) send(transcript);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
    }
  };

  const stopSpeaking = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    recognitionRef.current?.stop();
    setListening(false);
  };

  const headlines = briefing.data?.headlines ?? [];

  return (
    <section className="reporter-agent-console">
      <div className="reporter-agent-grid" />
      <div className="reporter-agent-orb">
        <span />
        <span />
        <span />
      </div>

      <header className="relative z-10 flex flex-col gap-3 border-b border-white/[0.08] pb-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] text-accent-cyan/78">
            E-yAy Brain / Raporcu Agent
          </div>
          <h2 className="mt-2 font-display text-2xl leading-none text-white md:text-3xl">
            Sor, sistemi okusun ve cevaplasin
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/56">
            Mevcut backend state, briefing ve chat endpointlerinden okur. Emir uretmez;
            cevabi yazili verir, ses aciksa tarayicida okur.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setVoiceEnabled((value) => !value)}
            disabled={!speechReady}
            className={`rounded-full border px-3 py-2 text-[10px] uppercase tracking-widest transition-colors ${
              voiceEnabled && speechReady
                ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                : "border-white/10 bg-white/[0.035] text-white/45"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            Ses {voiceEnabled && speechReady ? "acik" : "kapali"}
          </button>
          <button
            type="button"
            onClick={startListening}
            disabled={!micReady || listening || chat.isPending}
            className={`rounded-full border px-3 py-2 text-[10px] uppercase tracking-widest transition-colors ${
              listening
                ? "border-red-400/45 bg-red-400/10 text-red-300"
                : "border-accent-cyan/35 bg-accent-cyan/8 text-accent-cyan"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            {listening ? "Dinliyor" : "Mikrofon"}
          </button>
          <button
            type="button"
            onClick={stopSpeaking}
            className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 text-[10px] uppercase tracking-widest text-white/55 transition-colors hover:border-white/20 hover:text-white"
          >
            Sustur
          </button>
        </div>
      </header>

      <div className="relative z-10 mt-4 grid min-h-0 gap-4 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-3">
          <div className="rounded-2xl border border-accent-cyan/20 bg-black/28 p-4 shadow-[0_0_34px_rgba(34,211,238,0.1)]">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-white/38">
                  Canli briefing
                </div>
                <div className="mt-1 text-sm text-white/80">
                  {briefing.data?.regime_label ?? "Rejim okunuyor"}
                </div>
              </div>
              <div className="text-right text-[10px] uppercase tracking-widest text-white/36">
                {briefing.isLoading
                  ? "yukleniyor"
                  : briefing.data?.generated_at
                    ? fmtRelative(briefing.data.generated_at)
                    : "cycle bekleniyor"}
              </div>
            </div>
            <div className="space-y-2">
              {headlines.slice(0, 4).map((item, index) => (
                <div
                  key={`${item.category}-${index}`}
                  className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2"
                >
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-accent-cyan/72">
                    <span className="h-1.5 w-1.5 rounded-full bg-accent-cyan shadow-[0_0_12px_currentColor]" />
                    {CATEGORY_LABEL[item.category] ?? item.category}
                  </div>
                  <div className="mt-1 text-sm leading-5 text-white/84">{item.title}</div>
                  {item.detail ? (
                    <div className="mt-1 text-xs leading-5 text-white/48">{item.detail}</div>
                  ) : null}
                </div>
              ))}
              {!headlines.length ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-3 text-sm text-white/50">
                  Briefing bekleniyor. Backend cycle tamamlaninca burada basliklar gorunur.
                </div>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {QUICK_PROMPTS.slice(0, 4).map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => send(prompt)}
                disabled={chat.isPending}
                className="min-h-[58px] rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-left text-xs leading-5 text-white/70 transition-colors hover:border-accent-cyan/30 hover:bg-accent-cyan/8 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>

        <div className="flex min-h-[430px] flex-col rounded-2xl border border-white/10 bg-[#030811]/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-white/38">
                Cevap kanali
              </div>
              <div className="mt-1 text-sm text-white/80">
                Yazili cevap + opsiyonel sesli okuma
              </div>
            </div>
            <div className="reporter-wave" aria-hidden>
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {messages.length === 0 ? (
              <div className="rounded-2xl border border-accent-cyan/18 bg-accent-cyan/[0.045] p-4">
                <div className="text-[10px] uppercase tracking-widest text-accent-cyan/72">
                  Son rapor
                </div>
                <p className="mt-2 text-sm leading-6 text-white/72">{latestAgentText}</p>
                <button
                  type="button"
                  onClick={() => speak(latestAgentText)}
                  disabled={!speechReady}
                  className="mt-3 rounded-full border border-accent-cyan/30 bg-accent-cyan/8 px-3 py-1.5 text-[10px] uppercase tracking-widest text-accent-cyan disabled:opacity-40"
                >
                  Sesli oku
                </button>
              </div>
            ) : (
              messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`rounded-2xl px-3 py-2 text-sm leading-6 ${
                    message.role === "user"
                      ? "ml-8 border border-accent-cyan/28 bg-accent-cyan/10 text-cyan-100"
                      : message.meta?.refused
                        ? "mr-8 border border-red-400/30 bg-red-400/10 text-red-100"
                        : "mr-8 border border-white/10 bg-white/[0.045] text-white/74"
                  }`}
                >
                  {message.text}
                  {message.role === "agent" && message.meta?.evidence_used?.length ? (
                    <div className="mt-2 text-[10px] uppercase tracking-widest text-white/32">
                      kanit: {message.meta.evidence_used.slice(0, 3).join(" / ")}
                    </div>
                  ) : null}
                </div>
              ))
            )}
            {chat.isPending ? (
              <div className="rounded-2xl border border-accent-cyan/20 bg-accent-cyan/8 px-3 py-2 text-xs uppercase tracking-widest text-accent-cyan/76">
                Sistem state okunuyor...
              </div>
            ) : null}
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              send(input);
            }}
            className="mt-3 flex gap-2"
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ornek: 15 dakikalik firsat var mi?"
              maxLength={2000}
              className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/28 px-3 py-3 text-sm text-white/82 outline-none placeholder:text-white/30 focus:border-accent-cyan/45"
            />
            <button
              type="submit"
              disabled={chat.isPending || !input.trim()}
              className="rounded-xl border border-accent-cyan/35 bg-accent-cyan/10 px-4 py-3 text-xs uppercase tracking-widest text-accent-cyan transition-colors hover:bg-accent-cyan/16 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Sor
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
