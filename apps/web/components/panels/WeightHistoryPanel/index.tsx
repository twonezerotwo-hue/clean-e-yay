"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRebalanceProposal } from "@/lib/queries/hooks";
import {
  selectActiveVersion,
  selectHistory,
} from "@/lib/selectors/rebalance";
import { fmtRelative } from "@/lib/format";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "bg-amber-400/20 text-amber-400",
  APPROVED: "bg-signal-up/20 text-signal-up",
  REJECTED: "bg-signal-down/20 text-signal-down",
};

export function WeightHistoryPanel() {
  const { data, isLoading } = useRebalanceProposal();
  if (isLoading) {
    return (
      <PanelFrame id="weight_history">
        <PanelHeader title="Ağırlık Geçmişi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const items = selectHistory(data);
  const active = selectActiveVersion(data);
  if (!items.length) {
    return (
      <PanelFrame id="weight_history">
        <PanelHeader title="Ağırlık Geçmişi" subtitle={`aktif v${active}`} />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="weight_history">
      <PanelHeader
        title="Ağırlık Geçmişi"
        subtitle={`aktif v${active} · ${items.length} kayıt`}
      />
      <ul className="space-y-1.5 text-xs">
        {items.map((h, i) => (
          <li
            key={`${h.to_version}-${i}`}
            className="flex items-center justify-between border-b border-white/5 pb-1"
          >
            <span className="flex items-center gap-2">
              <span className="font-medium tabular-nums">
                v{h.from_version} → v{h.to_version}
              </span>
              <span className="text-white/40">{h.regime}</span>
            </span>
            <span className="flex items-center gap-2">
              <span
                className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
                  STATUS_COLOR[h.status] ?? "bg-white/10 text-white/40"
                }`}
              >
                {h.status}
              </span>
              <span className="text-white/40">{fmtRelative(h.generated_at)}</span>
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
