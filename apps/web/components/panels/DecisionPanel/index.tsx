"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { useAIReport, useDashboardState } from "@/lib/queries/hooks";
import { RISK_ACTION_COLOR, DIRECTION_COLOR } from "@/lib/constants";

export function DecisionPanel() {
  const ai = useAIReport();
  const dash = useDashboardState();
  return (
    <PanelFrame id="decision">
      <PanelHeader
        title="Karar Merkezi"
        subtitle="AI verdict + risk kapısı"
        actions={
          <DataQualityBadge
            dqs={dash.data?.meta.dqs_score}
            generatedAt={dash.data?.meta.generated_at}
            fallback={dash.data?.meta.fallback_used}
          />
        }
      />
      {ai.isLoading || dash.isLoading ? (
        <LoadingState />
      ) : !ai.data || !dash.data ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-white/40">
              AI Verdict
            </div>
            <div
              className={`text-2xl font-display mt-1 ${
                DIRECTION_COLOR[ai.data.verdict] ?? "text-white"
              }`}
            >
              {ai.data.verdict.toUpperCase()}
            </div>
            <p className="text-sm text-white/70 mt-2 line-clamp-4">
              {ai.data.narrative}
            </p>
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest text-white/40">
              Risk Kapısı
            </div>
            <div
              className={`text-2xl font-display mt-1 ${
                RISK_ACTION_COLOR[dash.data.risk_gate.action] ?? "text-white"
              }`}
            >
              {dash.data.risk_gate.action}
            </div>
            <p className="text-sm text-white/70 mt-2">
              {dash.data.risk_gate.reason}
            </p>
          </div>
        </div>
      )}
    </PanelFrame>
  );
}
