"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useAIReport } from "@/lib/queries/hooks";
import { DIRECTION_COLOR } from "@/lib/constants";

export function AIReportPanel() {
  const { data, isLoading } = useAIReport();
  return (
    <PanelFrame id="ai_report">
      <PanelHeader
        title="AI Analist Raporu"
        subtitle={data?.token_usage?.cached ? "cache" : "yeni"}
      />
      {isLoading ? (
        <LoadingState />
      ) : !data ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          <div className={`text-sm font-medium ${DIRECTION_COLOR[data.verdict] ?? "text-white"}`}>
            verdict: {data.verdict}
          </div>
          <p className="text-sm text-white/70 leading-relaxed">{data.narrative}</p>
          {data.key_signals?.length ? (
            <ul className="text-xs text-white/60 list-disc list-inside space-y-1">
              {data.key_signals.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </PanelFrame>
  );
}
