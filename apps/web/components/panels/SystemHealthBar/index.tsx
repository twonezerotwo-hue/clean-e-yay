"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import {
  useDashboardState,
  useDataSnapshot,
  useHealth,
  useSystemHealth,
} from "@/lib/queries/hooks";
import { selectModuleHealthList } from "@/lib/selectors/dashboard";
import { fmtRelative } from "@/lib/format";
import type { WorkerHealth } from "@/types/generated/api";

const COLOR: Record<string, string> = {
  ok: "bg-signal-up/20 text-signal-up",
  degraded: "bg-amber-400/20 text-amber-400",
  down: "bg-signal-down/20 text-signal-down",
};

// O1 — worker status → renk tonu (backend türetir; frontend hesap yapmaz).
const WORKER_TONE: Record<string, string> = {
  OK: "bg-signal-up/20 text-signal-up",
  DEGRADED: "bg-amber-400/20 text-amber-400",
  RUNNING: "bg-cyan-400/20 text-cyan-300",
  NO_DATA: "bg-white/10 text-white/50",
  STALE: "bg-amber-400/20 text-amber-400",
  FAILED: "bg-signal-down/20 text-signal-down",
  UNKNOWN: "bg-white/10 text-white/40",
};

function WorkerChip({ w }: { w?: WorkerHealth }) {
  if (!w) return null;
  return (
    <span
      className={`text-[10px] uppercase tracking-widest rounded px-2 py-1 ${
        WORKER_TONE[w.status] ?? "bg-white/10 text-white/40"
      }`}
      title={
        w.last_error
          ? `last_error: ${w.last_error}`
          : `cycle ${w.cycle_count} · ${w.age_seconds ?? "—"}s önce`
      }
    >
      {w.worker_name} · {w.status}
      {w.stale ? " · STALE" : ""}
    </span>
  );
}

export function SystemHealthBar() {
  const health = useHealth();
  const dash = useDashboardState();
  const snap = useDataSnapshot();
  const sys = useSystemHealth();
  const modules = selectModuleHealthList(dash.data);
  const dqsStatus = snap.data?.dqs.status;
  const dqsTone =
    dqsStatus === "BLOCKED"
      ? "bg-signal-down/20 text-signal-down"
      : dqsStatus === "DEGRADED"
      ? "bg-amber-400/20 text-amber-400"
      : dqsStatus === "OK"
      ? "bg-signal-up/20 text-signal-up"
      : "bg-white/10 text-white/40";

  const s = sys.data;
  const tick = s?.workers?.tick_worker;
  const learning = s?.workers?.learning_worker;
  const warnings = s?.warnings ?? [];

  return (
    <PanelFrame id="system_health">
      <PanelHeader
        title="Sistem Sağlığı"
        subtitle={
          health.data
            ? `API ${health.data.status} · uptime ${Math.round(health.data.uptime_sec)}s`
            : "API kontrol ediliyor…"
        }
        actions={
          <span className="rounded px-1.5 py-0.5 bg-white/5 text-white/50 ring-1 ring-white/10 uppercase tracking-wide text-[10px]">
            NO_EXECUTION
          </span>
        }
      />

      {/* O1 — worker reliability satırı (heartbeat-backed). */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <WorkerChip w={tick} />
        <WorkerChip w={learning} />
        {s ? (
          <span className="text-[10px] text-white/40">
            son tick {fmtRelative(s.last_successful_tick ?? null)} · son learning{" "}
            {fmtRelative(s.last_learning_run ?? null)} ·{" "}
            {s.snapshot_store_status &&
            typeof (s.snapshot_store_status as Record<string, unknown>)
              .snapshot_count === "number"
              ? `${
                  (s.snapshot_store_status as Record<string, number>).snapshot_count
                } snapshot`
              : "snapshot —"}
          </span>
        ) : null}
      </div>

      {warnings.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {warnings.map((w) => (
            <span
              key={w}
              className="text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5 bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30"
            >
              {w}
            </span>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {dqsStatus ? (
          <span
            className={`text-[10px] uppercase tracking-widest rounded px-2 py-1 ${dqsTone}`}
          >
            data · {dqsStatus}
          </span>
        ) : null}
        {modules.length === 0 ? (
          <span className="text-xs text-white/40">modül listesi yok</span>
        ) : (
          modules.map((m) => (
            <span
              key={m.id}
              className={`text-[10px] uppercase tracking-widest rounded px-2 py-1 ${
                COLOR[m.status] ?? "bg-white/10 text-white/50"
              }`}
            >
              {m.id} · {m.status}
            </span>
          ))
        )}
      </div>
    </PanelFrame>
  );
}
