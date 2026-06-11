"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRegimeReport } from "@/lib/queries/hooks";
import { selectTopAssets } from "@/lib/selectors/regime";
import { DIRECTION_COLOR } from "@/lib/constants";

const STATUS_COLOR: Record<string, string> = {
  CONFIRMED: "text-signal-up",
  PENDING: "text-amber-400",
  BLOCKING: "text-signal-down",
};

export function CommandSignalsPanel() {
  const { data, isLoading } = useRegimeReport();
  if (isLoading) {
    return (
      <PanelFrame id="command_signals">
        <PanelHeader title="Komuta Sinyalleri" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const assets = selectTopAssets(data, 8);
  if (!assets.length) {
    return (
      <PanelFrame id="command_signals">
        <PanelHeader title="Komuta Sinyalleri" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="command_signals">
      <PanelHeader title="Komuta Sinyalleri" subtitle={`${assets.length} varlık`} />
      <ul className="space-y-1.5 text-sm">
        {assets.map((a) => (
          <li
            key={a.symbol}
            className="flex items-center justify-between border-b border-white/5 pb-1"
          >
            <span className="font-medium">{a.symbol}</span>
            <span className="flex items-center gap-3">
              <span className={DIRECTION_COLOR[a.direction]}>{a.direction}</span>
              <span className={STATUS_COLOR[a.status]}>{a.status}</span>
              <span className="text-white/40">{a.score.toFixed(0)}</span>
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
