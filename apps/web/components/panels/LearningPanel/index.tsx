"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { CalibrationGrid } from "@/components/charts/CalibrationGrid";
import { useLearningSummary } from "@/lib/queries/hooks";
import { fmtPct, fmtNum } from "@/lib/format";

export function LearningPanel() {
  const { data, isLoading } = useLearningSummary();
  if (isLoading) {
    return (
      <PanelFrame id="learning">
        <PanelHeader title="Öğrenme" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data) {
    return (
      <PanelFrame id="learning">
        <PanelHeader title="Öğrenme" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="learning">
      <PanelHeader
        title="Öğrenme"
        subtitle={`${data.total_trades} işlem · weights ${data.weights_version ?? "—"}`}
      />
      <div className="grid grid-cols-3 gap-3 text-xs mb-3">
        <Stat label="Win Rate" value={fmtPct(data.win_rate)} />
        <Stat label="Sharpe" value={fmtNum(data.sharpe)} />
        <Stat label="Sortino" value={fmtNum(data.sortino)} />
      </div>
      {data.walk_forward ? (
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-2">
          walk-forward · test win {fmtPct(data.walk_forward.test_win_rate)} ·
          sharpe {fmtNum(data.walk_forward.test_sharpe)}
        </div>
      ) : null}
      <CalibrationGrid bins={data.calibration ?? []} />
    </PanelFrame>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-white/40">{label}</div>
      <div className="text-sm text-white/90">{value}</div>
    </div>
  );
}
