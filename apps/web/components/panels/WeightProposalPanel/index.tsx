"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRebalanceProposal } from "@/lib/queries/hooks";
import {
  selectActiveVersion,
  selectPending,
  selectTopDeltas,
} from "@/lib/selectors/rebalance";
import { fmtNum, fmtRelative } from "@/lib/format";

/**
 * G2 — Auto-weight trainer önerisi. Owner approval olmadan canlı ağırlık
 * değişmez. Bu panel sadece görünüm; approve/reject API çağrıları v2.
 */
export function WeightProposalPanel() {
  const { data, isLoading } = useRebalanceProposal();
  if (isLoading) {
    return (
      <PanelFrame id="weight_proposal">
        <PanelHeader title="Ağırlık Önerisi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const active = selectActiveVersion(data);
  const p = selectPending(data);
  if (!p) {
    return (
      <PanelFrame id="weight_proposal">
        <PanelHeader title="Ağırlık Önerisi" subtitle={`aktif v${active}`} />
        <EmptyState />
        <p className="mt-2 text-[11px] text-white/40">
          Yeterli doğrulanmış trade yok — trainer öneri üretmedi.
        </p>
      </PanelFrame>
    );
  }
  const deltas = selectTopDeltas(p.deltas, 6);
  return (
    <PanelFrame id="weight_proposal">
      <PanelHeader
        title="Ağırlık Önerisi"
        subtitle={`aktif v${active} → öneri v${p.to_version} · ${p.regime}`}
        actions={
          <span className="rounded px-1.5 py-0.5 bg-amber-400/20 text-amber-400 text-[10px] uppercase tracking-widest">
            owner approval bekliyor
          </span>
        }
      />
      <div className="text-[11px] text-white/50 mb-2">
        {p.dataset_size} verified trade · {p.rejected_records} kayıt
        atlandı · {fmtRelative(p.generated_at)}
      </div>
      <ul className="space-y-1 text-xs">
        {deltas.map((d) => {
          const positive = d.delta > 0;
          return (
            <li
              key={d.module}
              className="flex items-center justify-between border-b border-white/5 pb-1"
            >
              <span className="font-medium uppercase tracking-wide">
                {d.module}
              </span>
              <span className="flex items-center gap-3 tabular-nums">
                <span className="text-white/50">{fmtNum(d.old, 3)}</span>
                <span className="text-white/30">→</span>
                <span className="text-white/80">{fmtNum(d.new, 3)}</span>
                <span
                  className={
                    positive
                      ? "text-signal-up"
                      : d.delta < 0
                      ? "text-signal-down"
                      : "text-white/40"
                  }
                >
                  {positive ? "+" : ""}
                  {fmtNum(d.delta, 3)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[11px] text-white/40">{p.audit_note}</p>
    </PanelFrame>
  );
}
