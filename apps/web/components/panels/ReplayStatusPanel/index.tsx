"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { useReplayStatus } from "@/lib/queries/hooks";
import { fmtRelative } from "@/lib/format";
import {
  selectReplayActive,
  selectReplayCount,
  selectReplayModeBadge,
} from "@/lib/selectors/replay";

export function ReplayStatusPanel() {
  const { data } = useReplayStatus();
  // R1 — replay = kaydedilmiş gerçek state'in incelenmesi; sahte backtest yok.
  const active = selectReplayActive(data);
  const count = selectReplayCount(data);
  const badge = selectReplayModeBadge(data);
  return (
    <PanelFrame id="replay_status">
      <PanelHeader title="Replay Durumu" subtitle={`${count} snapshot`} />
      <div className="text-xs space-y-2 text-white/70">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`inline-block rounded px-2 py-0.5 text-[10px] font-semibold ${
              badge.tone === "active"
                ? "bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/30"
                : "bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30"
            }`}
          >
            {badge.label}
          </span>
          <span className="inline-block rounded px-2 py-0.5 text-[10px] font-semibold bg-white/5 text-white/50 ring-1 ring-white/10">
            NO LIVE EXECUTION
          </span>
        </div>
        <ul className="space-y-1">
          <li>
            store status: <span className="text-white/90">{data?.status ?? "—"}</span>
          </li>
          <li>
            snapshot_count: <span className="text-white/90">{count}</span>
          </li>
          <li>
            latest snapshot_id:{" "}
            <span className="text-white/90 break-all">
              {data?.latest_snapshot_id ?? "—"}
            </span>
          </li>
          <li>latest generated_at: {fmtRelative(data?.latest_generated_at ?? undefined)}</li>
        </ul>
        {data?.reason ? <p className="text-[11px] text-white/50">{data.reason}</p> : null}
        {!active ? (
          <p className="text-[11px] text-amber-300/70">
            Replay does not execute trades — yeterli kayıtlı snapshot olmadan
            backtest aktif değil; sahte geçmiş üretilmez.
          </p>
        ) : null}
      </div>
    </PanelFrame>
  );
}
