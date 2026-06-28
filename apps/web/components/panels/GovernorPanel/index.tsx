"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import {
  useGenerateGovernorTasks,
  useGovernorReport,
} from "@/lib/queries/hooks";
import type { GovernorReport } from "@/types/generated/api";

// Governor — self-managing katmanın özet panosu (packages/governor/report.py).
// "Agent bugün ne öğrendi / ne buldu / ne öneriyor / ne onay bekliyor / hangi
// veriye güvenmiyor" — hepsi read-only ViewModel'den. Frontend hesap YAPMAZ.
// PAPER_SAFE / NO_EXECUTION: governor trade açmaz, ayar değiştirmez.

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function GovernorPanel() {
  const { data, isLoading } = useGovernorReport();
  const generate = useGenerateGovernorTasks();

  if (isLoading) {
    return (
      <PanelFrame id="governor">
        <PanelHeader title="Governor" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d = data as GovernorReport | undefined;
  const run = rec(d?.worker_last_run?.data);
  const tasks = rec(d?.tasks?.data);
  const proposals = rec(d?.proposals?.data);
  const trust = rec(d?.data_trust?.data);
  const providers = rec(trust.providers);
  const dqs = rec(trust.dqs);

  const runStatus = typeof run.status === "string" ? run.status : "—";
  const generatedAt = typeof run.completed_at === "string" ? run.completed_at : null;
  const queueCount = num(tasks.queue_count) ?? 0;
  const pendingCount = num(proposals.pending_count) ?? 0;
  const degraded = num(providers.degraded_count);
  const dqsStatus = typeof dqs.status === "string" ? dqs.status : null;

  return (
    <PanelFrame id="governor">
      <PanelHeader
        title="Governor"
        subtitle="Öz-yönetim özeti — gözlemler, öğrenir, önerir (owner onayı bekler)"
        actions={
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10 disabled:opacity-50"
          >
            {generate.isPending ? "Üretiliyor…" : "Görev üret"}
          </button>
        }
      />

      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        Governor işlem açmaz, ayar değiştirmez. Yalnızca görev üretir, read-only
        rapor toplar ve owner onayına öneri sunar.
      </p>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Son koşu" value={runStatus} />
        <Stat label="Bekleyen görev" value={String(queueCount)} />
        <Stat label="Bekleyen öneri" value={String(pendingCount)} tone={pendingCount > 0 ? "warn" : undefined} />
        <Stat
          label="Veri güveni"
          value={dqsStatus ?? "—"}
          tone={degraded != null && degraded > 0 ? "warn" : undefined}
        />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-white/60">
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-1">
          <span className="text-white/40">Üretilen / koşulan görev: </span>
          <span className="tabular-nums">
            {num(run.tasks_generated) ?? 0} / {num(run.tasks_executed) ?? 0}
          </span>
        </div>
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-1">
          <span className="text-white/40">Degraded provider: </span>
          <span className="tabular-nums">{degraded ?? "—"}</span>
        </div>
      </div>

      {generatedAt ? (
        <div className="mt-2 text-[10px] uppercase tracking-widest text-white/30">
          Son koşu: {generatedAt}
        </div>
      ) : null}
    </PanelFrame>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn";
}) {
  return (
    <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-center">
      <div
        className={`text-sm font-semibold tabular-nums ${
          tone === "warn" ? "text-amber-300" : "text-white/80"
        }`}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-white/45">{label}</div>
    </div>
  );
}
