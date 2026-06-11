"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDashboardState } from "@/lib/queries/hooks";
import { selectAgentQuorum } from "@/lib/selectors/dashboard";
import { DIRECTION_COLOR } from "@/lib/constants";
import { fmtPct } from "@/lib/format";

const LABEL: Record<string, string> = {
  analyst: "Analist",
  risk_officer: "Risk Subayı",
  macro_strategist: "Makro Stratejist",
};

export function AgentVotesPanel() {
  const { data, isLoading } = useDashboardState();
  if (isLoading) {
    return (
      <PanelFrame id="agent_votes">
        <PanelHeader title="Agent Oyları" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data) {
    return (
      <PanelFrame id="agent_votes">
        <PanelHeader title="Agent Oyları" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const q = selectAgentQuorum(data);
  return (
    <PanelFrame id="agent_votes">
      <PanelHeader
        title="Agent Oyları"
        subtitle={q.quorumReached ? "quorum sağlandı" : "quorum yok"}
      />
      <ul className="space-y-2">
        {q.votes.map((v) => (
          <li key={v.persona} className="flex items-center justify-between text-sm">
            <span className="text-white/70">{LABEL[v.persona] ?? v.persona}</span>
            <span className="flex items-center gap-2">
              <span className={DIRECTION_COLOR[v.direction] ?? "text-white"}>
                {v.direction}
              </span>
              <span className="text-white/40">{fmtPct(v.confidence)}</span>
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
