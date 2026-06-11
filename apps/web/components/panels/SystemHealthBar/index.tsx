"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import {
  useDashboardState,
  useDataSnapshot,
  useHealth,
} from "@/lib/queries/hooks";
import { selectModuleHealthList } from "@/lib/selectors/dashboard";

const COLOR: Record<string, string> = {
  ok: "bg-signal-up/20 text-signal-up",
  degraded: "bg-amber-400/20 text-amber-400",
  down: "bg-signal-down/20 text-signal-down",
};

export function SystemHealthBar() {
  const health = useHealth();
  const dash = useDashboardState();
  const snap = useDataSnapshot();
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
  return (
    <PanelFrame id="system_health">
      <PanelHeader
        title="Sistem Sağlığı"
        subtitle={
          health.data
            ? `API ${health.data.status} · uptime ${Math.round(health.data.uptime_sec)}s`
            : "API kontrol ediliyor…"
        }
      />
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
