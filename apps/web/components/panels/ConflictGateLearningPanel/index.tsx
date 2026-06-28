"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import {
  useConflictGateStatus,
  useConflictGateValidation,
} from "@/lib/queries/hooks";
import { fmtNum, fmtPct } from "@/lib/format";
import type { ConflictGateRouteStats } from "@/types/generated/api";

type ValidationRow = {
  profile: string;
  route: string;
  n: number;
  win_rate: number;
  avg_pnl: number;
};

function isRouteStats(value: unknown): value is ConflictGateRouteStats {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ConflictGateRouteStats).n === "number" &&
    typeof (value as ConflictGateRouteStats).win_rate === "number" &&
    typeof (value as ConflictGateRouteStats).avg_pnl === "number"
  );
}

function validationRows(report: ReturnType<typeof useConflictGateValidation>["data"]) {
  const rows: ValidationRow[] = [];
  for (const [profile, value] of Object.entries(report ?? {})) {
    if (typeof value !== "object" || value === null) continue;
    for (const [route, stats] of Object.entries(value)) {
      if (!isRouteStats(stats)) continue;
      rows.push({ profile, route, ...stats });
    }
  }
  return rows.sort((a, b) => b.n - a.n);
}

function modeTone(mode: string) {
  if (mode === "HARD" || mode === "HARD_MANUAL") return "bg-signal-down/20 text-signal-down";
  if (mode === "SOFT" || mode === "SOFT_PLUS") return "bg-amber-400/20 text-amber-300";
  return "bg-white/10 text-white/55";
}

function routeTone(route: string) {
  if (route.includes("block")) return "text-signal-down";
  if (route.includes("open")) return "text-signal-up";
  if (route.includes("manual")) return "text-amber-300";
  return "text-white/70";
}

export function ConflictGateLearningPanel() {
  const status = useConflictGateStatus();
  const validation = useConflictGateValidation();
  const modes = Object.entries(status.data?.profile_modes ?? {});
  const rows = validationRows(validation.data);

  if (status.isLoading || validation.isLoading) {
    return (
      <PanelFrame id="conflict_gate_learning">
        <PanelHeader title="Conflict Gate Learning" />
        <LoadingState />
      </PanelFrame>
    );
  }

  if (!status.data && !rows.length) {
    return (
      <PanelFrame id="conflict_gate_learning">
        <PanelHeader title="Conflict Gate Learning" />
        <EmptyState />
      </PanelFrame>
    );
  }

  return (
    <PanelFrame id="conflict_gate_learning">
      <PanelHeader
        title="Conflict Gate Learning"
        subtitle={`${modes.length} profil modu / ${rows.length} validation route`}
        actions={
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-widest ${
              status.data?.enabled
                ? "bg-signal-up/20 text-signal-up"
                : "bg-white/10 text-white/55"
            }`}
          >
            {status.data?.enabled ? "ENABLED" : "SHADOW"}
          </span>
        }
      />

      {modes.length ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {modes.map(([profile, mode]) => (
            <span
              key={profile}
              className={`rounded border border-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${modeTone(
                mode,
              )}`}
            >
              {profile}: {mode}
            </span>
          ))}
        </div>
      ) : null}

      {!rows.length ? (
        <EmptyState message="Validation kaydi yok." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[24rem] border-collapse text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-white/40">
                <th className="p-1 text-left font-normal">Profil</th>
                <th className="p-1 text-left font-normal">Route</th>
                <th className="p-1 font-normal">N</th>
                <th className="p-1 font-normal">Win</th>
                <th className="p-1 text-right font-normal">Avg PnL</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 12).map((row) => (
                <tr key={`${row.profile}:${row.route}`} className="border-t border-white/5">
                  <td className="p-1 font-medium uppercase tracking-wide text-white/70">
                    {row.profile}
                  </td>
                  <td className={`p-1 font-mono text-[11px] ${routeTone(row.route)}`}>
                    {row.route}
                  </td>
                  <td className="p-1 text-center tabular-nums text-white/65">{row.n}</td>
                  <td className="p-1 text-center tabular-nums text-white/75">
                    {fmtPct(row.win_rate, 0)}
                  </td>
                  <td
                    className={`p-1 text-right tabular-nums ${
                      row.avg_pnl > 0
                        ? "text-signal-up"
                        : row.avg_pnl < 0
                          ? "text-signal-down"
                          : "text-white/55"
                    }`}
                  >
                    {fmtNum(row.avg_pnl, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelFrame>
  );
}
