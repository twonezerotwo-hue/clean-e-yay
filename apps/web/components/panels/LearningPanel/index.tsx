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
        <PanelHeader title="Öğrenme Özeti" />
        <LoadingState />
      </PanelFrame>
    );
  }

  if (!data) {
    return (
      <PanelFrame id="learning">
        <PanelHeader title="Öğrenme Özeti" />
        <EmptyState />
      </PanelFrame>
    );
  }

  const insufficient = data.sample_sufficient === false;
  const sampleCount = data.verified_outcomes ?? data.total_trades;
  const outcomeCount = data.outcomes_total ?? data.total_trades;

  return (
    <PanelFrame id="learning">
      <PanelHeader
        title="Öğrenme Özeti"
        subtitle={`${sampleCount}/${outcomeCount} doğrulanmış işlem · ağırlık sürümü ${data.weights_version ?? "---"}`}
        actions={
          insufficient ? (
            <span className="rounded px-1.5 py-0.5 bg-amber-400/20 text-amber-300 uppercase tracking-wide text-[10px]">
              LOW SAMPLE
            </span>
          ) : undefined
        }
      />

      {insufficient ? (
        <p className="mb-3 rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[11px] text-amber-200/90">
          Learning inactive - insufficient verified closed trades
          {data.min_sample ? ` (${sampleCount}/${data.min_sample})` : ""}.
        </p>
      ) : null}

      <div
        className={`grid grid-cols-4 gap-3 text-xs mb-3 ${
          insufficient ? "opacity-50" : ""
        }`}
      >
        <Stat label="Recent" value={String(data.total_trades)} />
        <Stat label="Win Rate" value={insufficient ? "---" : fmtPct(data.win_rate)} />
        <Stat label="Sharpe" value={insufficient ? "---" : fmtNum(data.sharpe)} />
        <Stat label="Sortino" value={insufficient ? "---" : fmtNum(data.sortino)} />
      </div>

      {data.walk_forward ? (
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-2">
          walk-forward - test win {fmtPct(data.walk_forward.test_win_rate)} - sharpe{" "}
          {fmtNum(data.walk_forward.test_sharpe)}
        </div>
      ) : null}

      {data.by_timeframe && Object.keys(data.by_timeframe).length > 0 ? (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
            Timeframe ayrimi
          </div>
          <div className="space-y-0.5">
            {Object.entries(data.by_timeframe).map(([tf, b]) => (
              <div key={tf} className="flex justify-between text-[11px] text-white/70">
                <span className="uppercase tracking-wide text-white/50">{tf}</span>
                <span>
                  {b.trades} islem - win {fmtPct(b.win_rate)} - pnl{" "}
                  {fmtNum(b.total_pnl)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {data.worker_last_run ? (
        <div className="mb-2 text-[10px] uppercase tracking-widest text-white/40">
          worker {data.worker_last_run.status} - {data.worker_last_run.outcomes_seen} outcome
          - proposal {data.proposal_status ?? "---"}
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
