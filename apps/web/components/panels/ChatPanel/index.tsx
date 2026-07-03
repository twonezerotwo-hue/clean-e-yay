"use client";

import { useState } from "react";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useChat } from "@/lib/queries/hooks";
import type { ChatResponse } from "@/types/generated/api";

type ChatItem = { role: "user" | "agent"; text: string; meta?: ChatResponse };

const SUGGESTIONS = [
  "RiskGate neyi engelledi?",
  "BTC 1h neden hold?",
  "Options risk ne diyor?",
  "Volatility neden kısıtladı?",
  "Funding / türev ne diyor?",
  "Hangi veri eksik?",
];

export function ChatPanel() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const chat = useChat();

  const send = (message: string) => {
    const text = message.trim();
    if (!text || chat.isPending) return;
    // Son turlar LLM bağlamına gider — takip sorusu bağlamıyla anlaşılır.
    const history = items
      .slice(-6)
      .filter((m) => m.text.trim())
      .map((m) => ({ role: m.role, text: m.text.slice(0, 500) }));
    setItems((xs) => [...xs, { role: "user", text }]);
    setInput("");
    chat.mutate({ message: text, history }, {
      onSuccess: (res) =>
        setItems((xs) => [...xs, { role: "agent", text: res.answer, meta: res }]),
      onError: () =>
        setItems((xs) => [
          ...xs,
          { role: "agent", text: "API'ye ulaşılamadı — yanıt üretilemedi." },
        ]),
    });
  };

  return (
    <PanelFrame id="chat">
      <PanelHeader title="Agent'a Sor" subtitle="state-grounded · LLM karar vermez" />
      <div className="space-y-2">
        <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
          {items.length === 0 ? (
            <div className="space-y-1">
              <p className="text-xs text-white/50">
                Agent'ın mevcut state'i hakkında soru sor:
              </p>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="block w-full text-left text-xs text-accent-cyan/80 hover:text-accent-cyan border border-ink-700/60 rounded-md px-2 py-1"
                >
                  {s}
                </button>
              ))}
            </div>
          ) : (
            items.map((m, i) => (
              <div
                key={i}
                className={`text-xs leading-relaxed rounded-lg px-2.5 py-1.5 ${
                  m.role === "user"
                    ? "bg-accent-cyan/10 text-accent-cyan/90 ml-6"
                    : m.meta?.refused
                      ? "bg-signal-down/10 text-signal-down/90 mr-2 border border-signal-down/40"
                      : "bg-ink-900/60 text-white/75 mr-2"
                }`}
              >
                {m.text}
                {m.role === "agent" && m.meta?.evidence_used?.length ? (
                  <div className="mt-1 text-[10px] text-white/35">
                    kanıt: {m.meta.evidence_used.slice(0, 3).join(" · ")}
                  </div>
                ) : null}
                {m.role === "agent" && m.meta?.llm ? (
                  <div className="text-[10px] text-white/30">
                    {m.meta.llm.source === "llm"
                      ? `LLM_GENERATED · ${m.meta.llm.model ?? ""}`
                      : m.meta.llm.source === "guard"
                        ? "GUARD"
                        : "DETERMINISTIC"}
                  </div>
                ) : null}
              </div>
            ))
          )}
          {chat.isPending ? (
            <div className="text-[10px] text-white/40">yanıt bekleniyor…</div>
          ) : null}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex gap-1.5"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Soru yaz…"
            maxLength={2000}
            className="flex-1 bg-ink-900/60 border border-ink-700/60 rounded-md px-2 py-1.5 text-xs text-white/80 placeholder:text-white/30 focus:outline-none focus:border-accent-cyan/50"
          />
          <button
            type="submit"
            disabled={chat.isPending || !input.trim()}
            className="text-xs px-2.5 py-1.5 rounded-md border border-accent-cyan/40 text-accent-cyan disabled:opacity-40"
          >
            Sor
          </button>
        </form>
      </div>
    </PanelFrame>
  );
}
