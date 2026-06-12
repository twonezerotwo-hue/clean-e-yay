"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { useAIReport, useDashboardState, useDecisionMatrix } from "@/lib/queries/hooks";
import {
  selectMatrixFirstSymbol,
  selectMatrixSuspended,
  selectTfStripFor,
} from "@/lib/selectors/decision";
import { RISK_ACTION_COLOR, DIRECTION_COLOR } from "@/lib/constants";
import type { TimeframeDecision } from "@/types/generated/api";

// T2 — mini TF strip: candidate→final + blocked_by tooltip'te; rozetler
// backend ViewModel'inden gelir.
function TfStrip() {
  const { data } = useDecisionMatrix();
  const symbol = selectMatrixFirstSymbol(data);
  const cells = symbol ? selectTfStripFor(data, symbol) : [];
  if (!cells.length) return null;
  const suspended = selectMatrixSuspended(data);
  return (
    <div className="mt-3 flex items-center gap-1.5 text-[10px]">
      <span className="uppercase tracking-widest text-white/40 mr-1">
        {symbol} TF
      </span>
      {cells.map((c: TimeframeDecision) => (
        <span
          key={c.timeframe}
          className={`rounded border px-1.5 py-0.5 tabular-nums ${
            c.status === "SUSPENDED"
              ? "border-signal-down/40 text-signal-down/80"
              : c.status === "ACTIONABLE"
                ? c.action === "open_long"
                  ? "border-signal-up/50 text-signal-up"
                  : "border-accent-magenta/50 text-accent-magenta"
                : "border-white/10 text-white/45"
          }`}
          title={`${c.candidate_action ?? "?"} → ${c.action} · ${
            c.blocked_by?.join(", ") || "açık"
          } · ${c.reason ?? ""}`}
        >
          {c.timeframe} {Math.round(c.score ?? 0)}
        </span>
      ))}
      {suspended ? (
        <span className="text-signal-down uppercase tracking-wide">
          SUSPENDED
        </span>
      ) : null}
    </div>
  );
}

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
            <TfStrip />
          </div>
        </div>
      )}
    </PanelFrame>
  );
}
