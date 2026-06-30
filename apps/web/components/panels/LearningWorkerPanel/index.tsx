"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useLearningSummary, useSystemHealth } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";
import type { LearningWorkerRun, WorkerHealth } from "@/types/generated/api";

function statusTone(status?: string | null, stale?: boolean) {
  if (stale) return "bg-amber-400/20 text-amber-300";
  if (status === "OK" || status === "RUNNING") return "bg-signal-up/20 text-signal-up";
  if (status === "FAILED" || status === "DOWN") return "bg-signal-down/20 text-signal-down";
  return "bg-white/10 text-white/55";
}

function ageText(seconds?: number | null) {
  if (seconds == null) return "--";
  if (seconds < 90) return `${Math.round(seconds)}sn`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}dk`;
  return `${Math.round(seconds / 3600)}sa`;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-white/10 bg-white/[0.025] px-2 py-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className="mt-1 truncate font-mono text-sm tabular-nums text-white/82">
        {value}
      </div>
    </div>
  );
}

function RunRows({ run }: { run: LearningWorkerRun | null | undefined }) {
  if (!run) {
    return (
      <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-xs text-white/40">
        Son learning run kaydi yok.
      </div>
    );
  }

  const extra = run as LearningWorkerRun & Record<string, unknown>;
  const rows: Array<[string, string]> = [
    ["Run", run.run_id],
    ["Status", run.status],
    ["Outcomes", String(run.outcomes_seen)],
    ["Proposal", String(run.proposals_generated)],
    ["Calibration", run.calibration_status],
    ["TF Calibration", String(extra.tf_calibration_status ?? "--")],
    ["TF Weights", String(extra.tf_weight_proposal_status ?? "--")],
    ["TF Target", String(extra.tf_target_status ?? "--")],
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[20rem] border-collapse text-xs">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-t border-white/5 first:border-t-0">
              <td className="p-1 text-[10px] uppercase tracking-widest text-white/38">
                {label}
              </td>
              <td className="p-1 text-right font-mono text-white/75">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {run.errors?.length ? (
        <div className="mt-2 rounded border border-signal-down/30 bg-signal-down/5 px-2 py-1.5 text-[11px] leading-5 text-signal-down/90">
          {run.errors.slice(0, 3).map((err) => (
            <div key={err}>{err}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function LearningWorkerPanel() {
  const health = useSystemHealth();
  const summary = useLearningSummary();
  const worker: WorkerHealth | undefined = health.data?.workers?.learning_worker;
  const run = summary.data?.worker_last_run;

  if (health.isLoading || summary.isLoading) {
    return (
      <PanelFrame id="learning_worker">
        <PanelHeader title="Öğrenme Motoru Durumu" />
        <LoadingState />
      </PanelFrame>
    );
  }

  if (!worker && !run) {
    return (
      <PanelFrame id="learning_worker">
        <PanelHeader title="Öğrenme Motoru Durumu" />
        <EmptyState message="Worker saglik verisi yok." />
      </PanelFrame>
    );
  }

  return (
    <PanelFrame id="learning_worker">
      <PanelHeader
        title="Öğrenme Motoru Durumu"
        subtitle={`son başarılı çalışma ${fmtRelative(worker?.last_success_at ?? health.data?.last_learning_run)}`}
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${statusTone(
              worker?.status,
              worker?.stale,
            )}`}
          >
            {worker?.stale ? "STALE" : worker?.status ?? run?.status ?? "UNKNOWN"}
          </span>
        }
      />

      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        <Metric label="Cycle" value={worker?.cycle_count ?? "--"} />
        <Metric label="Age" value={ageText(worker?.age_seconds)} />
        <Metric label="Outcomes" value={worker?.learning_outcomes_seen ?? run?.outcomes_seen ?? "--"} />
        <Metric label="Proposals" value={worker?.proposals_generated ?? run?.proposals_generated ?? "--"} />
      </div>

      <RunRows run={run} />

      {worker?.last_error ? (
        <div className="mt-2 rounded border border-signal-down/30 bg-signal-down/5 px-2 py-1.5 text-[11px] text-signal-down/90">
          {worker.last_error}
        </div>
      ) : null}
    </PanelFrame>
  );
}
