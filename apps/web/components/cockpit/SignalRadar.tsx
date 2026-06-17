// apps/web/components/cockpit/SignalRadar.tsx
"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import type { AgentBrief } from "@/types/generated/api";
import { DIRECTION_COLOR } from "@/lib/constants";

// KATMAN 1 — Holographic Signal Radar (Faz 1: veri-odaklı grid = ASIL bileşen).
// Faz 2'de bunun ÜSTÜNE mevcut CommandSignalsPanel'in R3F/holografik kabuğu
// opsiyonel olarak eklenir; kabuk hata verirse bu grid zaten fallback olur.
// Karar üretmez, trade açmaz — top_candidates'i (backend) gösterir.

export function SignalRadar({ brief }: { brief: AgentBrief }) {
  const cands = brief.top_candidates ?? [];
  const riskBlocked = !brief.can_act && brief.main_blocker.code === "RISK_GATE";
  const limited = brief.data_mode !== "LIVE_VERIFIED";

  return (
    <PanelFrame id="layer1_signal_radar">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-accent-cyan/60">
            Holographic Signal Radar
          </div>
          <div className="text-[11px] text-white/45">
            Raw asset signals · technical score · RiskGate-aware · no execution
          </div>
        </div>
        <div className="flex items-center gap-2">
          {limited ? (
            <span className="rounded px-1.5 py-0.5 text-[10px] bg-amber-400/15 text-amber-400">
              Data limited
            </span>
          ) : null}
          <span className="rounded px-1.5 py-0.5 text-[10px] bg-white/5 text-white/50 ring-1 ring-white/10">
            PAPER_SAFE
          </span>
        </div>
      </div>

      {cands.length ? (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {cands.map((c, i) => (
            <div key={i} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
              <div className="flex items-center justify-between">
                <span className="font-display text-sm text-white/90">{c.symbol ?? "—"}</span>
                <span className="text-[10px] text-white/40">{c.timeframe ?? ""}</span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className={`text-xs ${DIRECTION_COLOR[c.direction ?? "neutral"]}`}>
                  {c.direction ?? "neutral"}
                </span>
                <span className="text-lg font-display tabular-nums text-white/85">
                  {Math.round(c.score ?? 0)}
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${
                    c.actionable ? "bg-signal-up/15 text-signal-up" : "bg-white/5 text-white/45"
                  }`}
                >
                  {c.actionable ? "ACTIONABLE" : "RAW"}
                </span>
                {riskBlocked ? (
                  <span className="rounded px-1.5 py-0.5 text-[10px] bg-accent-magenta/15 text-accent-magenta">
                    Blocked by RiskGate
                  </span>
                ) : null}
              </div>
              <div className="mt-1 text-[10px] text-white/40">
                aday: {c.candidate_action ?? "—"} → final: {c.final_action ?? "—"}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-white/40">Radar boş — şu an izlenen aday yok.</p>
      )}

      <div className="mt-3 text-[10px] uppercase tracking-widest text-white/25">
        Faz 2: CommandSignalsPanel R3F holografik kabuğu opsiyonel olarak eklenecek
      </div>
    </PanelFrame>
  );
}
