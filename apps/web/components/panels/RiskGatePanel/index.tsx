"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { EvidenceList } from "@/components/tables/EvidenceList";
import { useDashboardState } from "@/lib/queries/hooks";
import { RISK_ACTION_COLOR } from "@/lib/constants";

export function RiskGatePanel() {
  const { data, isLoading } = useDashboardState();
  return (
    <PanelFrame id="risk_gate">
      <PanelHeader title="Risk Kapısı" subtitle="DQS + tetikleyici + rejim" />
      {isLoading ? (
        <LoadingState />
      ) : !data ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          <div className={`text-lg font-display ${RISK_ACTION_COLOR[data.risk_gate.action] ?? "text-white"}`}>
            {data.risk_gate.action}
          </div>
          <div className="text-xs text-white/60">{data.risk_gate.reason}</div>
          <EvidenceList items={data.risk_gate.evidence} />
        </div>
      )}
    </PanelFrame>
  );
}
