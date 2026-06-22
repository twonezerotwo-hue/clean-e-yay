"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  useAgentBriefing,
  useChat,
  useClosePaperPosition,
  useDataSnapshot,
  usePaperTradingState,
} from "@/lib/queries/hooks";
import { api } from "@/lib/api/client";
import { fmtRelative } from "@/lib/format";
import { selectDqs, selectSnapshotMeta } from "@/lib/selectors/snapshot";
import type { AgentBriefing, ChatResponse } from "@/types/generated/api";
import {
  Layer0HumanComputerModel,
  type Layer0DataQualityPulse,
} from "./Layer0HumanComputerModel";

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

/** Center "ilk ekran" karar paneli için CockpitView'den gelen hazır veriler. */
type ScanItem = { label: string; value: string; ok: boolean; href?: string };
export type Layer0HeroProps = {
  title: string;
  detail: string;
  tone: string;
  status: { label: string; tone: string };
  dqs: { value: string; tone: string };
  candidates: number;
  positions: number;
  scans: { veri: ScanItem; risk: ScanItem; sinyal: ScanItem; ticket: ScanItem };
  watch: { key: string; label: string }[];
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
    .replace(/[•·]/g, ".")
    .trim()
    .slice(0, 900);
}

function shortLine(text: string, max = 148) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}...` : clean;
}

/** Tarama satırı: layer'a yönlendiren buton veya /dashboard link'i. */
function ScanRow({
  item,
  onClick,
}: {
  item: ScanItem;
  onClick?: () => void;
}) {
  const dot = item.ok ? "bg-signal-up text-signal-up" : "bg-amber-400 text-amber-400";
  const badge = item.ok ? "text-signal-up" : "text-amber-300";
  const body = (
    <>
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full shadow-[0_0_14px_currentColor] ${dot}`} />
      <span className="min-w-0">
        <span className="block truncate text-xs text-white/82">{item.label}</span>
        <span className="block truncate text-[10px] uppercase tracking-widest text-white/38">
          {item.value}
        </span>
      </span>
      <span className={`text-[10px] uppercase tracking-widest ${badge}`}>
        {item.ok ? "OK" : "IZLE"}
      </span>
    </>
  );
  const cls =
    "grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-left transition-colors hover:border-accent-cyan/35 hover:bg-white/[0.06]";
  if (item.href) {
    return (
      <a href={item.href} className={cls}>
        {body}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className={cls}>
      {body}
    </button>
  );
}

export function Layer0ReporterAgent({
  hero,
  onNavigate,
}: {
  hero: Layer0HeroProps;
  onNavigate: (layer: 0 | 1 | 2 | 3) => void;
}) {
  const briefing = useAgentBriefing();
  const chat = useChat();
  const paper = usePaperTradingState();
  const snapshot = useDataSnapshot();
  const closePosition = useClosePaperPosition();
  const [confirmCloseId, setConfirmCloseId] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [messages, setMessages] = useState<ReporterMessage[]>([]);
  const [input, setInput] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [dialogueMode, setDialogueMode] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [micReady, setMicReady] = useState(false);
  const [lastUserText, setLastUserText] = useState("");
  const dialogueModeRef = useRef(false);
  const listeningRef = useRef(false);
  const chatPendingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const speechRunRef = useRef(0);

  useEffect(() => {
    setMicReady(Boolean(getSpeechRecognition()));
    return () => {
      speechRunRef.current += 1;
      audioRef.current?.pause();
      audioRef.current = null;
      if (audioUrlRef.current) {
        window.URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      setSpeaking(false);
      setVoiceLoading(false);
      recognitionRef.current?.stop();
    };
  }, []);

  useEffect(() => {
    dialogueModeRef.current = dialogueMode;
  }, [dialogueMode]);

  useEffect(() => {
    listeningRef.current = listening;
  }, [listening]);

  useEffect(() => {
    chatPendingRef.current = chat.isPending;
  }, [chat.isPending]);

  const briefingData = briefing.data as AgentBriefingWithExecutive | undefined;
  const executive = briefingData?.executive ?? null;
  const engine = briefingData?.engine ?? null;

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

  const dataQualityPulse = useMemo<Layer0DataQualityPulse | null>(() => {
    const dqs = selectDqs(snapshot.data);
    if (!dqs) return null;
    const meta = selectSnapshotMeta(snapshot.data);
    const generatedAt = meta?.generated_at ? Date.parse(meta.generated_at) : NaN;
    const ageSeconds = Number.isFinite(generatedAt)
      ? Math.max(0, (Date.now() - generatedAt) / 1000)
      : null;
    return {
      score: dqs.score,
      status: dqs.status,
      freshness: dqs.freshness,
      completeness: dqs.completeness,
      drift: dqs.drift,
      reconciliation: dqs.reconciliation,
      decisionUsage: dqs.decision_usage,
      ageLabel: ageSeconds == null ? "snapshot bekleniyor" : `${fmtAge(ageSeconds)} önce`,
    };
  }, [snapshot.data]);

  const clearAudioPlayback = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      window.URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  };

  const speakWithBrowserFallback = (text: string) => {
    if (!voiceEnabled || typeof window === "undefined" || !("speechSynthesis" in window)) {
      return false;
    }
    clearAudioPlayback();
    window.speechSynthesis.cancel();
    setSpeaking(false);
    const utterance = new SpeechSynthesisUtterance(cleanForVoice(text));
    utterance.lang = "tr-TR";
    utterance.rate = 1.0;
    utterance.pitch = 1.02;
    const voices = window.speechSynthesis.getVoices();
    // Doğal/neural sesleri tercih et (Microsoft "Online (Natural)", Google,
    // wavenet…) — yoksa varsayılan robotik sese düş.
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
    utterance.onend = () => {
      setSpeaking(false);
      if (dialogueModeRef.current) {
        window.setTimeout(() => startListening(), 520);
      }
    };
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    return true;
  };

  const speak = async (text: string) => {
    const cleanText = cleanForVoice(text);
    if (!voiceEnabled || !cleanText || typeof window === "undefined") {
      return false;
    }

    const runId = speechRunRef.current + 1;
    speechRunRef.current = runId;
    setVoiceError(null);
    setVoiceLoading(true);
    setSpeaking(false);
    clearAudioPlayback();
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

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
        if (dialogueModeRef.current) {
          window.setTimeout(() => startListening(), 520);
        }
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
  };

  const send = (message: string) => {
    const text = message.trim();
    if (!text || chat.isPending) return;
    setLastUserText(text);
    setMessages((items) => [...items, { role: "user", text }]);
    setInput("");
    chat.mutate(text, {
      onSuccess: (response) => {
        setMessages((items) => [
          ...items,
          { role: "agent", text: response.answer, meta: response },
        ]);
        void speak(response.answer).then((spoke) => {
          if (!spoke && dialogueModeRef.current) {
            window.setTimeout(() => startListening(), 520);
          }
        });
      },
      onError: () => {
        const fallback =
          "API chat yaniti alinamadi. Katman 0 sadece mevcut backend verisine bagli calisir; baglanti gelince soruyu yeniden cevaplayabilirim.";
        setMessages((items) => [...items, { role: "agent", text: fallback }]);
        void speak(fallback).then((spoke) => {
          if (!spoke && dialogueModeRef.current) {
            window.setTimeout(() => startListening(), 520);
          }
        });
      },
    });
  };

  const startListening = () => {
    if (listeningRef.current || chatPendingRef.current) return;
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
    setDialogueMode(false);
    speechRunRef.current += 1;
    clearAudioPlayback();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    recognitionRef.current?.stop();
    setListening(false);
    setSpeaking(false);
    setVoiceLoading(false);
  };

  const toggleDialogueMode = () => {
    const next = !dialogueMode;
    setDialogueMode(next);
    if (next) {
      setVoiceEnabled(true);
      window.setTimeout(() => startListening(), 120);
    } else {
      stopSpeaking();
    }
  };

  const headlines = briefingData?.headlines ?? [];
  const modelMode = listening
    ? "listening"
    : chat.isPending
      ? "thinking"
      : voiceLoading
        ? "thinking"
        : speaking
          ? "speaking"
          : "idle";
  const stateLabel =
    modelMode === "speaking"
      ? "konusuyor"
      : modelMode === "listening"
        ? "dinliyor"
        : modelMode === "thinking"
          ? voiceLoading
            ? "ses hazirlaniyor"
            : "dusunuyor"
          : "hazir";
  const positions = paper.data?.open_positions ?? [];
  const totalPnl = paper.data?.unrealized_pnl_usd ?? 0;
  const subtitleSpeaker =
    modelMode === "listening"
      ? "SEN"
      : modelMode === "thinking"
        ? "ANALIZ"
        : modelMode === "speaking"
          ? "E-yAy"
          : dialogueMode
            ? "CANLI DIYALOG"
            : "E-yAy";
  const subtitleText =
    modelMode === "listening"
      ? "Dinliyorum. Sorunu bitirince otomatik olarak sisteme iletecegim."
      : modelMode === "thinking"
        ? lastUserText
          ? `Sorun okunuyor: ${shortLine(lastUserText, 110)}`
          : "Sistem state, haber, risk ve sinyal katmanlarini tararken bekle."
        : modelMode === "speaking"
          ? shortLine(latestAgentText, 132)
          : dialogueMode
            ? "Karsilikli mod acik. Konusma bitince tekrar dinlemeye donecegim."
            : shortLine(latestAgentText, 132);

  return (
    <section className="grid h-full min-h-0 gap-4 lg:grid-cols-[minmax(310px,0.92fr)_minmax(340px,1.04fr)_minmax(320px,1fr)]">
      {/* ── Sutun 1: Acik pozisyonlar + sistem durumu ───────────────── */}
      <div className="flex min-h-0 flex-col gap-4">
        <div className="layer0-card flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-white/[0.08] pb-3">
            <div className="text-sm font-semibold uppercase tracking-[0.18em] text-white/85">
              Acik Pozisyonlar
            </div>
            <div className="text-[11px] uppercase tracking-widest text-white/45">
              {paper.data
                ? `${positions.length} acik / sonuc ${totalPnl >= 0 ? "+" : ""}$${Math.round(
                    totalPnl,
                  ).toLocaleString()}`
                : "yukleniyor"}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {positions.length ? (
              <table className="w-full border-collapse text-sm">
                <thead className="sticky top-0 z-10 bg-[#040910]">
                  <tr className="text-left text-[10px] uppercase tracking-widest text-white/35">
                    <th className="py-2 pr-2 font-medium">Yon</th>
                    <th className="py-2 pr-2 font-medium">Sembol</th>
                    <th className="py-2 pr-2 font-medium">Zaman</th>
                    <th className="py-2 pr-2 font-medium">Boyut</th>
                    <th className="py-2 pr-2 text-right font-medium">P&amp;L (USD)</th>
                    <th className="py-2 text-right font-medium">Islem</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos) => {
                    const pnl = pos.unrealized_pnl_usd ?? 0;
                    const up = pnl >= 0;
                    const confirming = confirmCloseId === pos.id;
                    const closingThis = closePosition.isPending && confirming;
                    return (
                      <tr
                        key={pos.id}
                        className="border-b border-white/[0.05] last:border-0"
                      >
                        <td className="py-2 pr-2">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
                              pos.side === "long"
                                ? "bg-emerald-400/15 text-emerald-300"
                                : "bg-red-400/15 text-red-300"
                            }`}
                          >
                            {pos.side === "long" ? "AL" : "SAT"}
                          </span>
                        </td>
                        <td className="py-2 pr-2 font-semibold text-white/88">{pos.symbol}</td>
                        <td className="py-2 pr-2 text-[11px] uppercase tracking-widest text-white/45">
                          {pos.timeframe ?? "--"}
                        </td>
                        <td className="py-2 pr-2 text-[11px] tabular-nums text-white/55">
                          ${Math.round(pos.size_usd).toLocaleString()}
                        </td>
                        <td
                          className={`py-2 pr-2 text-right text-sm font-semibold tabular-nums ${
                            up ? "text-emerald-300" : "text-red-300"
                          }`}
                        >
                          {up ? "+" : ""}${Math.round(pnl).toLocaleString()}
                        </td>
                        <td className="py-2 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              if (!confirming) {
                                setConfirmCloseId(pos.id);
                                return;
                              }
                              closePosition.mutate(pos.id, {
                                onSettled: () => setConfirmCloseId(null),
                              });
                            }}
                            onBlur={() =>
                              confirming && !closePosition.isPending && setConfirmCloseId(null)
                            }
                            disabled={closePosition.isPending}
                            className={`rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-widest transition-colors disabled:opacity-40 ${
                              confirming
                                ? "border-red-400/55 bg-red-400/15 text-red-200"
                                : "border-white/12 bg-white/[0.04] text-white/55 hover:border-red-400/35 hover:text-red-200"
                            }`}
                          >
                            {closingThis ? "..." : confirming ? "Onayla" : "Kapat"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div className="mt-2 rounded-xl border border-white/10 bg-white/[0.035] px-3 py-3 text-sm text-white/50">
                Acik pozisyon yok. (Trade Ticket farkli: yeni sinyalin broker&apos;a devri;
                pozisyon = zaten acik islem.)
              </div>
            )}
          </div>
        </div>

        <div className="layer0-card">
          <div className="flex items-center justify-between gap-3 border-b border-white/[0.08] pb-3">
            <div className="text-sm font-semibold uppercase tracking-[0.18em] text-white/85">
              Sistem Durumu
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
                    ? `Motor ${engine.stale ? "BAYAT" : "CANLI"}`
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
          <div className="mt-3 space-y-2">
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
      </div>

      {/* ── Sutun 2: Human-computer model + karar hero ──────────────── */}
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
        <div className="reporter-model-card shrink-0">
          <Layer0HumanComputerModel mode={modelMode} dataQuality={dataQualityPulse} />
          <div className="reporter-model-hud">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-accent-cyan/76">
                human-computer
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
            <span>{stateLabel}</span>
            <span>{voiceEnabled ? "tts ready" : "audio off"}</span>
            <span>{micReady ? "mic ready" : "mic off"}</span>
          </div>
        </div>

        <div className="layer0-card shrink-0 text-center">
          <div className={`font-display text-4xl leading-none sm:text-5xl ${hero.tone}`}>
            {hero.title}
          </div>
          <div className="mt-3 text-sm leading-6 text-white/62">{hero.detail}</div>
        </div>

        <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">
          <HudMetric label="Durum" value={hero.status.label} tone={hero.status.tone} />
          <HudMetric label="DQS" value={hero.dqs.value} tone={hero.dqs.tone} />
          <HudMetric label="Aday" value={String(hero.candidates)} tone="text-emerald-200" />
          <HudMetric label="Pozisyon" value={String(hero.positions)} tone="text-amber-200" />
        </div>

        <div className="grid shrink-0 grid-cols-1 gap-2 sm:grid-cols-2">
          <ScanRow item={hero.scans.veri} onClick={() => onNavigate(3)} />
          <ScanRow item={hero.scans.risk} />
          <ScanRow item={hero.scans.sinyal} onClick={() => onNavigate(1)} />
          <ScanRow item={hero.scans.ticket} />
          {hero.watch.slice(0, 2).map((item) => (
            <div
              key={item.key}
              className="grid grid-cols-[auto_1fr] items-center gap-3 rounded-xl border border-white/10 bg-black/24 px-3 py-2"
            >
              <span className="h-2.5 w-2.5 rounded-full bg-accent-cyan/70 shadow-[0_0_12px_currentColor]" />
              <span className="min-w-0 truncate text-xs text-white/68">{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Sutun 3: Konusma paneli ─────────────────────────────────── */}
      <div className="layer0-card flex min-h-0 flex-col">
        <div className="flex items-center justify-between gap-2 border-b border-white/[0.08] pb-3">
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-white/85">
            <span className="grid h-6 w-6 place-items-center rounded-md border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan">
              ▢
            </span>
            Konusma Paneli
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setVoiceEnabled((value) => !value)}
              className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40 ${
                voiceEnabled
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                  : "border-white/10 bg-white/[0.035] text-white/45"
              }`}
            >
              Ses
            </button>
            <button
              type="button"
              onClick={startListening}
              disabled={!micReady || listening || chat.isPending}
              className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40 ${
                listening
                  ? "border-red-400/45 bg-red-400/10 text-red-300"
                  : "border-accent-cyan/35 bg-accent-cyan/8 text-accent-cyan"
              }`}
            >
              {listening ? "..." : "Mik"}
            </button>
            <button
              type="button"
              onClick={stopSpeaking}
              className="rounded-lg border border-white/10 bg-white/[0.035] px-2 py-1 text-[10px] uppercase tracking-widest text-white/55 transition-colors hover:border-white/20 hover:text-white"
            >
              Sus
            </button>
          </div>
        </div>

        <div className="mt-3 text-[10px] uppercase tracking-widest text-white/38">Cevap kanali</div>

        <div className="mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <div className="rounded-2xl border border-accent-cyan/18 bg-accent-cyan/[0.045] p-4">
              <div className="text-[10px] uppercase tracking-widest text-accent-cyan/72">
                Son rapor
              </div>
              <p className="mt-2 text-sm leading-6 text-white/72">{latestAgentText}</p>
              <button
                type="button"
                onClick={() => {
                  if (speaking || voiceLoading) {
                    stopSpeaking();
                  } else {
                    void speak(latestAgentText);
                  }
                }}
                disabled={!voiceEnabled}
                className="mt-3 rounded-full border border-accent-cyan/30 bg-accent-cyan/8 px-3 py-1.5 text-[10px] uppercase tracking-widest text-accent-cyan disabled:opacity-40"
              >
                {voiceLoading ? "Ses uretiliyor" : speaking ? "Durdur" : "Sesli oku"}
              </button>
              {voiceError ? (
                <div className="mt-2 text-[10px] uppercase tracking-widest text-amber-300/80">
                  {voiceError}
                </div>
              ) : null}
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`rounded-2xl px-3 py-2 text-sm leading-6 ${
                  message.role === "user"
                    ? "ml-6 border border-accent-cyan/28 bg-accent-cyan/10 text-cyan-100"
                    : message.meta?.refused
                      ? "mr-6 border border-red-400/30 bg-red-400/10 text-red-100"
                      : "mr-6 border border-white/10 bg-white/[0.045] text-white/74"
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

        <div className="mt-3 grid shrink-0 grid-cols-2 gap-2">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => send(prompt)}
              disabled={chat.isPending}
              className="min-h-[48px] rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-left text-[11px] leading-5 text-white/70 transition-colors hover:border-accent-cyan/30 hover:bg-accent-cyan/8 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {prompt}
            </button>
          ))}
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(input);
          }}
          className="mt-3 flex shrink-0 gap-2"
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
    </section>
  );
}

function HudMetric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/24 px-3 py-2 text-center">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-1 font-display text-lg leading-none tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}
