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
  // UX1 — örnek sayısı düşükse Sharpe/WinRate istatistiksel olarak güvenilmez;
  // büyük gösterme, uyarı bas (yeterlilik kararı backend'de — frontend hesap yapmaz).
  const insufficient = data.sample_sufficient === false;
  return (
    <PanelFrame id="learning">
      <PanelHeader
        title="Öğrenme"
        subtitle={`${data.total_trades} işlem · weights ${data.weights_version ?? "—"}`}
        actions={
          insufficient ? (
            <span className="rounded px-1.5 py-0.5 bg-amber-400/20 text-amber-300 uppercase tracking-wide text-[10px]">
              INSUFFICIENT SAMPLE
            </span>
          ) : undefined
        }
      />
      {insufficient ? (
        <p className="mb-3 rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[11px] text-amber-200/90">
          INSUFFICIENT SAMPLE — metrics not statistically reliable
          {data.min_sample ? ` (${data.total_trades}/${data.min_sample} işlem)` : ""}.
        </p>
      ) : null}
      <div
        className={`grid grid-cols-3 gap-3 text-xs mb-3 ${
          insufficient ? "opacity-50" : ""
        }`}
      >
        <Stat label="Win Rate" value={insufficient ? "—" : fmtPct(data.win_rate)} />
        <Stat label="Sharpe" value={insufficient ? "—" : fmtNum(data.sharpe)} />
        <Stat label="Sortino" value={insufficient ? "—" : fmtNum(data.sortino)} />
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
