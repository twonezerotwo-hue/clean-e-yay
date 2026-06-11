"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useDashboardState } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";

export function ReplayStatusPanel() {
  const { data } = useDashboardState();
  return (
    <PanelFrame id="replay_status">
      <PanelHeader title="Replay Durumu" />
      <ul className="text-xs space-y-1 text-white/70">
        <li>
          snapshot_id: <span className="text-white/90">{data?.meta.snapshot_id ?? "—"}</span>
        </li>
        <li>generated_at: {fmtRelative(data?.meta.generated_at)}</li>
        <li>quorum: {data?.quorum_reached ? "✓" : "—"}</li>
      </ul>
    </PanelFrame>
  );
}
