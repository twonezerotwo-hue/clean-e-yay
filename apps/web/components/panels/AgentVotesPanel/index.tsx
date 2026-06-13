"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useAIReport, useDashboardState } from "@/lib/queries/hooks";
import { selectPersonaSections } from "@/lib/selectors/ai";
import { selectAgentQuorum } from "@/lib/selectors/dashboard";
import { DIRECTION_COLOR } from "@/lib/constants";

// UX1 — agent kanıt zinciri: her agent için verdict + reason + evidence_used +
// missing_data + actionability. "Analist neutral 7.8%" yerine NEDEN. Persona
// bölümleri backend'den gelir (evidence_used LLM uyduramaz).

const LABEL: Record<string, string> = {
  analyst: "Analist",
  risk_officer: "Risk Subayı",
  macro_strategist: "Makro Stratejist",
};

export function AgentVotesPanel() {
  const ai = useAIReport();
  const dash = useDashboardState();
  if (ai.isLoading) {
    return (
      <PanelFrame id="agent_votes">
        <PanelHeader title="Agent Kanıt Zinciri" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const sections = selectPersonaSections(ai.data);
  if (!sections.length) {
    return (
      <PanelFrame id="agent_votes">
        <PanelHeader title="Agent Kanıt Zinciri" />
        <EmptyState />
      </PanelFrame>
    );
  }
  // Yön/güven dashboard agent_votes'tan (persona ile eşli) — verdict rozeti için.
  const votes = selectAgentQuorum(dash.data).votes;
  const dirOf = (persona: string) => votes.find((v) => v.persona === persona);

  return (
    <PanelFrame id="agent_votes">
      <PanelHeader title="Agent Kanıt Zinciri" subtitle="verdict · neden · kanıt" />
      <ul className="space-y-3 text-[11px]">
        {sections.map((s) => {
          const v = dirOf(s.persona);
          return (
            <li key={s.persona} className="border-b border-white/5 pb-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-white/85">
                  {LABEL[s.persona] ?? s.persona}
                </span>
                {v ? (
                  <span className={`uppercase ${DIRECTION_COLOR[v.direction] ?? "text-white"}`}>
                    {v.direction}
                  </span>
                ) : null}
              </div>
              <p className="text-white/70 mt-0.5">{s.summary}</p>
              {s.actionability ? (
                <p className="text-[10px] text-accent-cyan/80 mt-0.5">
                  ↳ {s.actionability}
                </p>
              ) : null}
              {s.evidence_used?.length ? (
                <p className="text-[10px] text-white/40 mt-0.5 break-all">
                  kanıt: {s.evidence_used.slice(0, 3).join(" · ")}
                </p>
              ) : null}
              {s.missing_data?.length ? (
                <p className="text-[10px] text-amber-400/70 mt-0.5">
                  eksik veri: {s.missing_data.slice(0, 2).join(" · ")}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </PanelFrame>
  );
}
