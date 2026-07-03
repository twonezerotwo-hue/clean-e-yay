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

      {data.cohorts ? (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
            Performans ayrımı — kim kazandı, kim kaybetti?
          </div>
          <div className="grid grid-cols-3 gap-2">
            <CohortCard
              title="OTOMATİK"
              hint="sistemin kendi işlemleri"
              stats={data.cohorts.auto}
              emphasized
            />
            <CohortCard
              title="MANUEL"
              hint="senin açtıkların"
              stats={data.cohorts.manual}
            />
            <CohortCard
              title="HARİÇ"
              hint="test / kaynağı belirsiz"
              stats={data.cohorts.excluded}
            />
          </div>
          {(data.cohorts.auto.manual_closed ?? 0) > 0 ? (
            <p className="mt-1 text-[10px] text-white/40">
              Otomatik açılan {data.cohorts.auto.manual_closed} işlemi owner kapattı —
              bunlar otomatik kolonda sayılır ama çıkış kararı sisteme ait değil.
            </p>
          ) : null}
        </div>
      ) : null}

      {data.walk_forward ? (
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-2">
          walk-forward - test win {fmtPct(data.walk_forward.test_win_rate)} - sharpe{" "}
          {fmtNum(data.walk_forward.test_sharpe)}
        </div>
      ) : null}

      {data.by_timeframe && Object.keys(data.by_timeframe).length > 0 ? (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
            Timeframe ayrımı (tüm işlemler · oto = sadece otomatik)
          </div>
          <div className="space-y-0.5">
            {Object.entries(data.by_timeframe).map(([tf, b]) => {
              const auto = data.cohorts?.auto.by_timeframe?.[tf];
              return (
                <div key={tf} className="flex justify-between text-[11px] text-white/70">
                  <span className="uppercase tracking-wide text-white/50">{tf}</span>
                  <span>
                    {b.trades} islem - win {fmtPct(b.win_rate)} - pnl{" "}
                    {fmtNum(b.total_pnl)}
                    {auto ? (
                      <span className={auto.total_pnl >= 0 ? "text-emerald-300/80" : "text-red-300/80"}>
                        {" "}· oto {fmtNum(auto.total_pnl)}
                      </span>
                    ) : null}
                  </span>
                </div>
              );
            })}
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

function CohortCard({
  title,
  hint,
  stats,
  emphasized = false,
}: {
  title: string;
  hint: string;
  stats: { trades: number; win_rate: number; total_pnl: number };
  emphasized?: boolean;
}) {
  const pnlTone = stats.total_pnl > 0 ? "text-emerald-300" : stats.total_pnl < 0 ? "text-red-300" : "text-white/60";
  return (
    <div
      className={`rounded border px-2 py-1.5 ${
        emphasized ? "border-sky-400/30 bg-sky-400/5" : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="text-[10px] uppercase tracking-widest text-white/50">{title}</div>
      <div className="text-[9px] text-white/35 mb-1">{hint}</div>
      <div className={`text-sm font-medium ${pnlTone}`}>{fmtNum(stats.total_pnl)}</div>
      <div className="text-[10px] text-white/50">
        {stats.trades} işlem{stats.trades > 0 ? ` · win ${fmtPct(stats.win_rate)}` : ""}
      </div>
    </div>
  );
}
