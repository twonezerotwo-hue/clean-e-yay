"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import {
  useGenerateGovernorTasks,
  useGovernorTasks,
  useRunGovernorTask,
} from "@/lib/queries/hooks";
import type { GovernorTasksView } from "@/types/generated/api";

const PRIO_TONE: Record<string, string> = {
  P0: "text-signal-down",
  P1: "text-amber-300",
  P2: "text-amber-200",
  P3: "text-white/60",
  P4: "text-white/45",
};

const TYPE_LABEL: Record<string, string> = {
  DATA_QUALITY_REVIEW: "Veri kalitesi incelemesi",
  RISK_REVIEW: "Risk incelemesi",
  MISSED_OPPORTUNITY_REVIEW: "Kaçan fırsat incelemesi",
  TRADE_REVIEW: "Trade sonucu incelemesi",
  MODE_REVIEW: "Mod ayarı incelemesi",
  SYSTEM_HEALTH_REVIEW: "Sistem sağlığı incelemesi",
};

const TYPE_DETAIL: Record<string, string> = {
  DATA_QUALITY_REVIEW: "Provider veya DQS tarafında güven düşüşü var; veri kaynağı raporu çalıştırılacak.",
  RISK_REVIEW: "Risk halt veya risk kapısı davranışı read-only raporla incelenecek.",
  MISSED_OPPORTUNITY_REVIEW: "Açılmayan valid setup sonuçları gözden geçirilecek.",
  TRADE_REVIEW: "Kapanan trade outcome'ları ve öğrenme özeti incelenecek.",
  MODE_REVIEW: "Aktif mod ve profil ayarları incelenecek.",
  SYSTEM_HEALTH_REVIEW: "Worker ve sistem sağlığı raporu üretilecek.",
};

export function TaskQueuePanel() {
  const { data, isLoading } = useGovernorTasks();
  const generate = useGenerateGovernorTasks();
  const run = useRunGovernorTask();

  if (isLoading) {
    return (
      <PanelFrame id="governor_tasks">
        <PanelHeader title="Bekleyen İncelemeler" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: GovernorTasksView | undefined = data;
  const queue = d?.queue ?? [];
  const history = d?.history ?? [];
  const busy = generate.isPending || run.isPending;

  return (
    <PanelFrame id="governor_tasks">
      <PanelHeader
        title="Bekleyen İncelemeler"
        subtitle={`${queue.length} bekleyen inceleme`}
        actions={
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={busy}
            className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10 disabled:opacity-50"
          >
            {generate.isPending ? "Üretiliyor…" : "Görev üret"}
          </button>
        }
      />

      {queue.length ? (
        <ul className="space-y-1.5">
          {queue.slice(0, 12).map((t) => (
            <li
              key={t.task_id}
              className="rounded border border-white/10 bg-white/[0.02] px-2 py-1.5"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-semibold ${PRIO_TONE[t.priority] ?? "text-white/50"}`}>
                      {t.priority}
                    </span>
                    <span className="truncate text-[11px] font-medium text-white/80">
                      {TYPE_LABEL[t.task_type] ?? t.task_type}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-white/50">
                    {TYPE_DETAIL[t.task_type] ?? t.subject ?? t.task_type}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => run.mutate(t.task_id)}
                  disabled={busy}
                  className="shrink-0 rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] text-white/70 hover:bg-white/10 disabled:opacity-50"
                >
                  {run.isPending ? "Çalışıyor…" : "Çalıştır"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/40">
          Bekleyen görev yok. Sistem taraması için Görev üret düğmesini kullan.
        </div>
      )}

      {history.length ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-white/35">
            Son çalıştırılanlar ({history.length})
          </summary>
          <ul className="mt-1 space-y-0.5 text-[11px] text-white/55">
            {history.slice(0, 8).map((t) => (
              <li key={t.task_id} className="flex justify-between gap-2">
                <span className="truncate">
                  <span className="text-white/35">{t.priority} · </span>
                  {TYPE_LABEL[t.task_type] ?? t.subject ?? t.task_type}
                </span>
                <span
                  className={
                    t.status === "DONE"
                      ? "text-signal-up"
                      : t.status === "FAILED"
                        ? "text-signal-down"
                        : "text-white/40"
                  }
                >
                  {t.status}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </PanelFrame>
  );
}
