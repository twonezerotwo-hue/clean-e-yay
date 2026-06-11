"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectDqs, selectSnapshotMeta } from "@/lib/selectors/snapshot";

const ROWS: { key: keyof NonNullable<ReturnType<typeof selectDqs>>; label: string }[] = [
  { key: "freshness", label: "Freshness" },
  { key: "completeness", label: "Completeness" },
  { key: "drift", label: "Drift" },
  { key: "reconciliation", label: "Reconciliation" },
  { key: "decision_usage", label: "Decision usage" },
];

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
          <DataQualityBadge
            dqs={dqs.score}
            generatedAt={meta?.generated_at}
            fallback={dqs.fallback_used}
          />
        }
      />
      <div className="space-y-2 text-xs">
        {ROWS.map((r) => (
          <div key={r.key} className="space-y-0.5">
            <div className="flex items-center justify-between">
              <span className="text-white/60">{r.label}</span>
              <span className="text-white/80 tabular-nums">
                {(dqs[r.key] as number).toFixed(0)}
              </span>
            </div>
            {bar(dqs[r.key] as number)}
          </div>
        ))}
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
