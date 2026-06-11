"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectDqs, selectSnapshotMeta } from "@/lib/selectors/snapshot";
import type { DqsStatus } from "@/types/generated/api";

const ROWS = [
  { key: "freshness", label: "Freshness" },
  { key: "completeness", label: "Completeness" },
  { key: "drift", label: "Drift" },
  { key: "reconciliation", label: "Reconciliation" },
  { key: "decision_usage", label: "Decision usage" },
] as const;

const STATUS_TONE: Record<DqsStatus, string> = {
  OK: "bg-signal-up/20 text-signal-up",
  DEGRADED: "bg-amber-400/20 text-amber-400",
  BLOCKED: "bg-signal-down/20 text-signal-down",
};

function bar(v: number) {
  const pct = Math.max(0, Math.min(100, v));
  const color =
    pct >= 75 ? "bg-signal-up" : pct >= 55 ? "bg-amber-400" : "bg-signal-down";
  return (
    <div className="h-1.5 w-full rounded bg-white/10 overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function DataQualityPanel() {
  const { data, isLoading } = useDataSnapshot();
  if (isLoading) {
    return (
      <PanelFrame id="data_quality">
        <PanelHeader title="Veri Kalitesi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const dqs = selectDqs(data);
  const meta = selectSnapshotMeta(data);
  if (!dqs) {
    return (
      <PanelFrame id="data_quality">
        <PanelHeader title="Veri Kalitesi" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="data_quality">
      <PanelHeader
        title="Veri Kalitesi"
        subtitle="DQS — 5 konsept"
        actions={
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${STATUS_TONE[dqs.status]}`}
            >
              {dqs.status}
            </span>
            <DataQualityBadge
              dqs={dqs.score}
              generatedAt={meta?.generated_at}
              fallback={dqs.fallback_used}
            />
          </div>
        }
      />
      <div className="space-y-2 text-xs">
        {ROWS.map((r) => (
          <div key={r.key} className="space-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-white/60">{r.label}</span>
              <span className="text-white/80 tabular-nums">
                {dqs[r.key].toFixed(0)}
              </span>
            </div>
            {bar(dqs[r.key])}
          </div>
        ))}
        {dqs.status === "BLOCKED" ? (
          <p className="mt-2 text-[11px] text-signal-down">
            Veri kalitesi yetersiz — yeni karar üretilmiyor. Sağlayıcı
            durumunu kontrol edin.
          </p>
        ) : null}
        {dqs.notes.length ? (
          <ul className="pt-2 space-y-0.5 text-[11px] text-white/50">
            {dqs.notes.map((n, i) => (
              <li key={i}>· {n}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </PanelFrame>
  );
}
