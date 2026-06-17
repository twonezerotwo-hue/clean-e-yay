// apps/web/components/cockpit/AgentBrainCard.tsx
"use client";

import { useState } from "react";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import type { AgentBrief } from "@/types/generated/api";
import {
  AGENT_STATUS_TONE,
  AGENT_STATUS_LABEL,
  BLOCKER_TONE,
  DATA_MODE_TONE,
} from "@/lib/selectors/cockpit";
import { CHANGE_SEVERITY_TONE } from "@/lib/selectors/cockpit-diff";
import { useBriefChanges } from "@/hooks/useBriefChanges";

// KATMAN 1 — Agent Brain. agent_brief.summary zaten backend'in konuşulabilir
// özeti; burada onu + son tick değişimlerini gösteririz. Karar üretmez.

export function AgentBrainCard({
  brief,
  generatedAt,
}: {
  brief: AgentBrief;
  generatedAt?: string;
}) {
  const { feed } = useBriefChanges(brief, generatedAt);
  const [speaking, setSpeaking] = useState(false);

  const speak = () => {
    // Web Speech — yalnızca kullanıcı basınca; otomatik ses YOK.
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(brief.summary);
    u.lang = "tr-TR";
    const tr = window.speechSynthesis.getVoices().find((v) => v.lang?.startsWith("tr"));
    if (tr) u.voice = tr;
    u.onend = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(u);
  };
  const stop = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window)
      window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  return (
    <PanelFrame id="layer1_agent_brain" className="border border-accent-cyan/20">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-[10px] uppercase tracking-widest text-accent-cyan/60">
            Agent Brain
          </span>
          <span className={`text-2xl font-display ${AGENT_STATUS_TONE[brief.status]}`}>
            {AGENT_STATUS_LABEL[brief.status] ?? brief.status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] uppercase tracking-widest ${DATA_MODE_TONE[brief.data_mode]}`}
          >
            {brief.data_mode}
          </span>
          <DataQualityBadge dqs={brief.dqs?.score ?? undefined} generatedAt={generatedAt} />
          <button
            onClick={speaking ? stop : speak}
            className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:text-white"
          >
            {speaking ? "Durdur" : "Dinle"}
          </button>
        </div>
      </div>

      <p className="text-sm text-white/85 leading-relaxed mt-3">{brief.summary}</p>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-[10px] uppercase tracking-widest text-white/40">Ana engel</span>
        <span className={`text-sm font-medium ${BLOCKER_TONE[brief.main_blocker.code]}`}>
          {brief.main_blocker.label}
        </span>
        <span className="text-[10px] uppercase tracking-widest text-accent-cyan/50 ml-1">
          Önerilen duruş
        </span>
        <span className="text-xs text-accent-cyan/90">{brief.recommended_stance}</span>
      </div>

      {/* Son tick değişimleri (frontend ref-diff) */}
      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
          Son değişimler
        </div>
        {feed.length ? (
          <ul className="space-y-1">
            {feed.slice(0, 5).map((c, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span
                  className={`text-[10px] font-semibold ${CHANGE_SEVERITY_TONE[c.severity]}`}
                >
                  {c.severity}
                </span>
                <span className="text-white/75">{c.title}</span>
                {c.before != null || c.after != null ? (
                  <span className="text-white/40 tabular-nums">
                    {String(c.before ?? "—")} → {String(c.after ?? "—")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-white/40">
            Baz alındı — bu oturumda henüz değişim yok.
          </p>
        )}
      </div>

      <div className="mt-3 text-[10px] uppercase tracking-widest text-white/30">
        Yalnızca okuma · PAPER_SAFE / NO_EXECUTION · karar = deterministik engine + RiskGate
      </div>
    </PanelFrame>
  );
}
