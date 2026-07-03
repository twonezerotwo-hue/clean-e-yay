"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import {
  useGenerateGovernorTasks,
  useGovernorReport,
} from "@/lib/queries/hooks";
import type { GovernorReport } from "@/types/generated/api";

const TASK_DETAIL: Record<string, string> = {
  DATA_QUALITY_REVIEW: "Provider veya DQS tarafında güven düşüşü var; veri kaynağı raporu çalıştırılacak.",
  RISK_REVIEW: "Risk halt veya risk kapısı davranışı read-only raporla incelenecek.",
  MISSED_OPPORTUNITY_REVIEW: "Açılmayan valid setup sonuçları gözden geçirilecek.",
  TRADE_REVIEW: "Kapanan trade outcome'ları ve öğrenme özeti incelenecek.",
  MODE_REVIEW: "Aktif mod ve profil ayarları incelenecek.",
  SYSTEM_HEALTH_REVIEW: "Worker ve sistem sağlığı raporu üretilecek.",
};

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
        <PanelHeader title="Sistem Yöneticisi" />
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
  const queue = Array.isArray(tasks.queue) ? tasks.queue : [];
  const nextTask = rec(queue[0]);

  const runStatus = typeof run.status === "string" ? run.status : "—";
  const generatedAt = typeof run.completed_at === "string" ? run.completed_at : null;
  const queueCount = num(tasks.queue_count) ?? 0;
  const pendingCount = num(proposals.pending_count) ?? 0;
  const degraded = num(providers.degraded_count);
  const dqsStatus = typeof dqs.status === "string" ? dqs.status : null;
  const generatedResult = rec(generate.data);
  const generatedCount = num(generatedResult.generated);
  const generatedMessage =
    generatedCount == null
      ? null
      : generatedCount > 0
        ? `Görev taraması tamamlandı: ${generatedCount} yeni görev hazır.`
        : queueCount > 0
          ? "Görev taraması tamamlandı: yeni görev yok; mevcut bekleyen görev aşağıda."
          : "Görev taraması tamamlandı: yeni görev yok.";
  const nextPriority = typeof nextTask.priority === "string" ? nextTask.priority : null;
  const nextType = typeof nextTask.task_type === "string" ? nextTask.task_type : null;
  const nextSubject = nextType ? TASK_DETAIL[nextType] : null;

  return (
    <PanelFrame id="governor">
      <PanelHeader
        title="Sistem Yöneticisi"
        subtitle="Görevlerini kendisi üretir ve koşar — 15 dk'da bir"
        actions={
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10 disabled:opacity-50"
          >
            {generate.isPending ? "Taranıyor…" : "Şimdi tara"}
          </button>
        }
      />

      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        Otomatik döngü: 15 dakikada bir sistemi tarar, gereken incelemeleri üretir ve
        kendisi koşar; sonuç raporları aşağıda birikir. İşlem açmaz, ayar değiştirmez
        — yalnızca okur ve owner onayına veri hazırlar.
      </p>

      {generatedMessage ? (
        <p className="mb-2 rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[11px] text-emerald-200/90">
          {generatedMessage}
        </p>
      ) : null}

      {generate.isError ? (
        <p className="mb-2 rounded border border-signal-down/30 bg-signal-down/5 px-2 py-1 text-[11px] text-signal-down/90">
          Görev üretimi tamamlanamadı.
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Son koşu" value={runStatus} />
        <Stat label="Bekleyen görev" value={String(queueCount)} tone={queueCount > 0 ? "warn" : undefined} />
        <Stat label="Bekleyen öneri" value={String(pendingCount)} tone={pendingCount > 0 ? "warn" : undefined} />
        <Stat
          label="Veri güveni"
          value={dqsStatus ?? "—"}
          tone={degraded != null && degraded > 0 ? "warn" : undefined}
        />
      </div>

      {nextType ? (
        <div className="mt-2 rounded border border-amber-400/25 bg-amber-400/8 px-2 py-1.5 text-[11px] text-white/70">
          <div className="mb-0.5 flex items-center justify-between gap-2">
            <span className="uppercase tracking-widest text-white/40">Sıradaki görev</span>
            <span className="font-mono text-amber-300">{nextPriority ?? "P?"}</span>
          </div>
          <div className="font-medium text-white/85">{nextType}</div>
          {nextSubject ? <div className="mt-0.5 text-white/50">{nextSubject}</div> : null}
          <div className="mt-1 text-[10px] uppercase tracking-widest text-white/35">
            Detay ve çalıştırma: aşağıdaki Görev Kuyruğu paneli
          </div>
        </div>
      ) : null}

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
