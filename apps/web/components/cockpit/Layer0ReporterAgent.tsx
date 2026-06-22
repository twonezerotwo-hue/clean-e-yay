"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useAgentBriefing, useChat, usePaperTradingState } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";
import type { AgentBriefing, ChatResponse } from "@/types/generated/api";
import { Layer0HumanComputerModel } from "./Layer0HumanComputerModel";

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

type ExecutiveBriefing = {
  tone: string;
  stance_label: string;
  headline: string;
  narrative: string;
  recommendation: string;
  flags?: string[];
};

type BriefingEngine = {
  stale?: boolean;
  age_seconds?: number | null;
};

type AgentBriefingWithExecutive = AgentBriefing & {
  executive?: ExecutiveBriefing | null;
  engine?: BriefingEngine | null;
};

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

const TONE_STYLE: Record<string, string> = {
  alert: "border-red-400/45 bg-red-400/10 text-red-200",
  warn: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  ok: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  info: "border-accent-cyan/35 bg-accent-cyan/8 text-accent-cyan",
};

const TONE_DOT: Record<string, string> = {
  alert: "bg-red-400",
  warn: "bg-amber-400",
  ok: "bg-emerald-400",
  info: "bg-accent-cyan",
};

function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null) return "bilinmiyor";
  if (seconds < 90) return `${Math.round(seconds)} sn`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} dk`;
  return `${(seconds / 3600).toFixed(1)} sa`;
}

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
    .replace(/[\u2022\u00b7]/g, ".")
    .trim()
    .slice(0, 900);
}

export function Layer0ReporterAgent() {
  const briefing = useAgentBriefing();
  const chat = useChat();
  const paper = usePaperTradingState();
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [messages, setMessages] = useState<ReporterMessage[]>([]);
  const [input, setInput] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [speechReady, setSpeechReady] = useState(false);
  const [micReady, setMicReady] = useState(false);

  useEffect(() => {
    setSpeechReady(typeof window !== "undefined" && "speechSynthesis" in window);
    setMicReady(Boolean(getSpeechRecognition()));
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      setSpeaking(false);
      recognitionRef.current?.stop();
    };
  }, []);

  const briefingData = briefing.data as AgentBriefingWithExecutive | undefined;
  const executive = briefingData?.executive ?? null;
  const engine = briefingData?.engine ?? null;
  const executiveFlags = executive?.flags ?? [];

  const briefingText = useMemo(() => {
    if (executive) {
      return `${executive.headline} ${executive.narrative} Tavsiyem: ${executive.recommendation}`;
    }
    const headlines = briefingData?.headlines ?? [];
    if (!headlines.length) return "Briefing bekleniyor. Bir sonraki veri cycle'i okunuyor.";
    return headlines
      .slice(0, 4)
      .map((item) => `${CATEGORY_LABEL[item.category] ?? item.category}: ${item.title}`)
      .join(". ");
  }, [briefingData?.headlines, executive]);

  const latestAgentText = useMemo(() => {
    const last = [...messages].reverse().find((item) => item.role === "agent");
    return last?.text ?? briefingText;
  }, [briefingText, messages]);

  const speak = (text: string) => {
    if (!voiceEnabled || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
    const utterance = new SpeechSynthesisUtterance(cleanForVoice(text));
    utterance.lang = "tr-TR";
    utterance.rate = 0.96;
    utterance.pitch = 0.92;
    const voices = window.speechSynthesis.getVoices();
    utterance.voice =
      voices.find((voice) => voice.lang.toLowerCase().startsWith("tr")) ??
      voices.find((voice) => voice.lang.toLowerCase().startsWith("en")) ??
      null;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
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
    setSpeaking(false);
  };

  const headlines = briefingData?.headlines ?? [];
  const modelMode = listening ? "listening" : chat.isPending ? "thinking" : speaking ? "speaking" : "idle";

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
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-accent-cyan/25 bg-accent-cyan/8 px-3 py-1 text-[10px] uppercase tracking-widest text-accent-cyan">
              {modelMode === "speaking"
                ? "konusuyor"
                : modelMode === "listening"
                  ? "dinliyor"
                  : modelMode === "thinking"
                    ? "dusunuyor"
                    : "hazir"}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1 text-[10px] uppercase tracking-widest text-white/52">
              state-grounded
            </span>
            <span className="rounded-full border border-amber-400/20 bg-amber-400/8 px-3 py-1 text-[10px] uppercase tracking-widest text-amber-300">
              no-execution
            </span>
          </div>
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

      <div className="relative z-10 mt-4 grid min-h-0 gap-4 2xl:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-3">
          <div className="reporter-model-card">
            <Layer0HumanComputerModel mode={modelMode} />
            <div className="reporter-model-hud">
              <div>
                <div className="text-[10px] uppercase tracking-[0.24em] text-accent-cyan/76">
                  human-computer model
                </div>
                <div className="mt-1 font-display text-xl leading-none text-white/92">
                  E-yAy Nexus
                </div>
              </div>
              <div className="reporter-model-spectrum" aria-hidden>
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
            </div>
            <div className="reporter-model-footer">
              <span>voice link</span>
              <span>{speechReady ? "audio ready" : "audio unavailable"}</span>
              <span>{micReady ? "mic ready" : "mic unavailable"}</span>
            </div>
          </div>

          {executive ? (
            <div
              className={`rounded-2xl border p-4 ${
                TONE_STYLE[executive.tone] ?? TONE_STYLE.info
              }`}
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${TONE_DOT[executive.tone] ?? TONE_DOT.info} shadow-[0_0_12px_currentColor]`}
                  />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.22em]">
                    {executive.stance_label}
                  </span>
                </div>
                <span className="text-[10px] uppercase tracking-widest opacity-70">
                  Patrona brifing
                </span>
              </div>
              <p className="text-sm font-semibold leading-6 text-white">
                {executive.headline}
              </p>
              <p className="mt-2 text-xs leading-6 text-white/72">{executive.narrative}</p>
              <p className="mt-2 text-xs leading-6 text-white/90">
                <span className="uppercase tracking-widest opacity-70">Tavsiyem:</span>{" "}
                {executive.recommendation}
              </p>
              {executiveFlags.length ? (
                <div className="mt-3 space-y-1 border-t border-white/10 pt-3">
                  {executiveFlags.map((flag, index) => (
                    <div key={index} className="flex items-start gap-2 text-[11px] leading-5 text-white/82">
                      <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-current" />
                      {flag}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-2xl border border-white/10 bg-black/28 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-[10px] uppercase tracking-widest text-white/38">
                Acik pozisyonlar
              </div>
              <div className="text-[10px] uppercase tracking-widest text-white/45">
                {paper.data
                  ? `${paper.data.open_positions.length} acik / sonuc ${
                      (paper.data.unrealized_pnl_usd ?? 0) >= 0 ? "+" : ""
                    }$${Math.round(paper.data.unrealized_pnl_usd ?? 0).toLocaleString()}`
                  : "yukleniyor"}
              </div>
            </div>
            <div className="space-y-1.5">
              {paper.data?.open_positions.length ? (
                paper.data.open_positions.map((pos) => {
                  const pnl = pos.unrealized_pnl_usd ?? 0;
                  const up = pnl >= 0;
                  return (
                    <div
                      key={pos.id}
                      className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2"
                    >
                      <div className="flex items-center gap-2 text-sm">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
                            pos.side === "long"
                              ? "bg-emerald-400/15 text-emerald-300"
                              : "bg-red-400/15 text-red-300"
                          }`}
                        >
                          {pos.side === "long" ? "AL" : "SAT"}
                        </span>
                        <span className="font-semibold text-white/88">{pos.symbol}</span>
                        <span className="text-[10px] uppercase tracking-widest text-white/40">
                          {pos.timeframe ?? "--"} / ${Math.round(pos.size_usd).toLocaleString()}
                        </span>
                      </div>
                      <span
                        className={`text-sm font-semibold tabular-nums ${
                          up ? "text-emerald-300" : "text-red-300"
                        }`}
                      >
                        {up ? "+" : ""}${Math.round(pnl).toLocaleString()}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-3 text-sm text-white/50">
                  Acik pozisyon yok. (Trade Ticket farkli sey: yeni sinyalin broker'a
                  devri; pozisyon = zaten acik islem.)
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-accent-cyan/20 bg-black/28 p-4 shadow-[0_0_34px_rgba(34,211,238,0.1)]">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-white/38">
                  Sistem durumu
                </div>
                <div className="mt-1 text-sm text-white/80">
                  {briefingData?.regime_label ?? "Rejim okunuyor"}
                </div>
              </div>
              <div className="text-right">
                <div
                  className={`text-[10px] font-semibold uppercase tracking-widest ${
                    engine?.stale ? "text-red-300" : "text-emerald-300"
                  }`}
                >
                  {briefing.isLoading
                    ? "yukleniyor"
                    : engine
                      ? `Motor ${engine.stale ? "BAYAT" : "canli"}`
                      : "cycle bekleniyor"}
                </div>
                <div className="mt-0.5 text-[10px] uppercase tracking-widest text-white/36">
                  {engine
                    ? `son cycle ${fmtAge(engine.age_seconds)} once`
                    : briefingData?.generated_at
                      ? fmtRelative(briefingData.generated_at)
                      : ""}
                </div>
              </div>
            </div>
            <div className="space-y-2">
              {headlines.slice(0, 4).map((item, index) => (
                <div
                  key={`${item.category}-${index}`}
                  className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2"
                >
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-white/55">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[item.tone] ?? TONE_DOT.info} shadow-[0_0_12px_currentColor]`}
                    />
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
