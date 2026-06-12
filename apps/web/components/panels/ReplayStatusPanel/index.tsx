"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useReplayStatus } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";

export function ReplayStatusPanel() {
  const { data } = useReplayStatus();
  // OPS — replay motoru rezerve; sahte replay yok. Durum dürüstçe gösterilir.
  const reserved = data ? !data.available : true;
  return (
    <PanelFrame id="replay_status">
      <PanelHeader title="Replay Durumu" />
      <div className="text-xs space-y-2 text-white/70">
        <span
          className={`inline-block rounded px-2 py-0.5 text-[10px] font-semibold ${
            reserved
              ? "bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30"
              : "bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/30"
          }`}
        >
          {data?.status === "reserved_not_active" ? "REZERVE · AKTİF DEĞİL" : (data?.status ?? "—")}
        </span>
        <ul className="space-y-1">
          <li>
            latest snapshot_id:{" "}
            <span className="text-white/90">{data?.latest_snapshot_id ?? "—"}</span>
          </li>
          <li>generated_at: {fmtRelative(data?.generated_at)}</li>
        </ul>
        {data?.reason ? <p className="text-[11px] text-white/50">{data.reason}</p> : null}
      </div>
    </PanelFrame>
  );
}
