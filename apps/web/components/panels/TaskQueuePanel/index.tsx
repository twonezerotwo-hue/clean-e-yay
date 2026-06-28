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

// Görev Kuyruğu (packages/governor/tasks.py) — agent'ın kendi ürettiği
// OBSERVE-ONLY görevler. DEĞİŞMEZ: görevler config/paper/RiskGate'e yazamaz
// (can_change_policy=false yapısal). Frontend hesap YAPMAZ. PAPER_SAFE.

const PRIO_TONE: Record<string, string> = {
  P0: "text-signal-down",
  P1: "text-amber-300",
  P2: "text-amber-200",
  P3: "text-white/60",
  P4: "text-white/45",
};

export function TaskQueuePanel() {
  const { data, isLoading } = useGovernorTasks();
  const generate = useGenerateGovernorTasks();
  const run = useRunGovernorTask();

  if (isLoading) {
    return (
      <PanelFrame id="governor_tasks">
        <PanelHeader title="Görev Kuyruğu" />
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
        title="Görev Kuyruğu"
        subtitle="Observe-only — yalnızca rapor üretir"
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
        <ul className="space-y-1">
          {queue.slice(0, 12).map((t) => (
            <li
              key={t.task_id}
              className="flex items-center justify-between gap-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1"
            >
              <span className="min-w-0">
                <span className={`mr-1.5 text-[10px] font-semibold ${PRIO_TONE[t.priority] ?? "text-white/50"}`}>
                  {t.priority}
                </span>
                <span className="text-[11px] text-white/75">{t.subject ?? t.task_type}</span>
              </span>
              <button
                type="button"
                onClick={() => run.mutate(t.task_id)}
                disabled={busy}
                className="shrink-0 rounded border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] text-white/70 hover:bg-white/10 disabled:opacity-50"
              >
                Koştur
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-[11px] text-white/35">
          Kuyruk boş. "Görev üret" ile sistemi taratabilirsin.
        </div>
      )}

      {history.length ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-white/35">
            Son koşulanlar ({history.length})
          </summary>
          <ul className="mt-1 space-y-0.5 text-[11px] text-white/55">
            {history.slice(0, 8).map((t) => (
              <li key={t.task_id} className="flex justify-between gap-2">
                <span className="truncate">
                  <span className="text-white/35">{t.priority} · </span>
                  {t.subject ?? t.task_type}
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
