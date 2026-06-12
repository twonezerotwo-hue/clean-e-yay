"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDataSnapshot } from "@/lib/queries/hooks";
import {
  selectSnapshotMeta,
  selectDqs,
  selectTfCoverage,
} from "@/lib/selectors/snapshot";
import { fmtRelative, fmtTime } from "@/lib/format";

export function SnapshotPanel() {
  const { data, isLoading } = useDataSnapshot();
  if (isLoading) {
    return (
      <PanelFrame id="snapshot">
        <PanelHeader title="Snapshot" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const meta = selectSnapshotMeta(data);
  const dqs = selectDqs(data);
  const tfCoverage = selectTfCoverage(data);
  if (!meta) {
    return (
      <PanelFrame id="snapshot">
        <PanelHeader title="Snapshot" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="snapshot">
      <PanelHeader title="Snapshot" subtitle={meta.snapshot_id} />
      <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
        <dt className="text-white/50">Oluşturuldu</dt>
        <dd className="text-right tabular-nums">{fmtTime(meta.generated_at)}</dd>

        <dt className="text-white/50">Tazelik</dt>
        <dd className="text-right">{fmtRelative(meta.generated_at)}</dd>

        <dt className="text-white/50">Semboller</dt>
        <dd className="text-right tabular-nums">{meta.symbols.length}</dd>

        <dt className="text-white/50">Fallback</dt>
        <dd className="text-right">
          {dqs?.fallback_used ? (
            <span className="text-signal-down">evet</span>
          ) : (
            <span className="text-signal-up">hayır</span>
          )}
        </dd>

        {tfCoverage ? (
          <>
            <dt className="text-white/50">TF teknikleri</dt>
            <dd className="text-right tabular-nums">
              <span
                className={
                  tfCoverage.ok === tfCoverage.total
                    ? "text-signal-up"
                    : "text-amber-400"
                }
              >
                {tfCoverage.ok}/{tfCoverage.total} OK
              </span>
            </dd>
          </>
        ) : null}
      </dl>
      {data?.warnings?.length ? (
        <ul className="mt-3 space-y-0.5 text-[11px] text-amber-400/80">
          {data.warnings.map((w, i) => (
            <li key={i}>· {w}</li>
          ))}
        </ul>
      ) : null}
    </PanelFrame>
  );
}
