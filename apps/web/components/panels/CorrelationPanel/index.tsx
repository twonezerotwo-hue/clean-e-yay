"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRiskCorrelation } from "@/lib/queries/hooks";
import {
  selectClusters,
  selectInsufficientPairs,
  selectLimits,
  selectMatrixGrid,
} from "@/lib/selectors/correlation";
import { fmtNum, fmtPct } from "@/lib/format";
import type { CorrelationEntry, ExposureCluster } from "@/types/generated/api";

const CLUSTER_TONE: Record<ExposureCluster["status"], string> = {
  BREACH: "bg-signal-down/20 text-signal-down",
  WARNING: "bg-amber-400/20 text-amber-400",
  OK: "bg-white/10 text-white/50",
};

// Neon tema: pozitif rho → cyan, negatif → magenta; |rho| → yoğunluk.
function cellStyle(e: CorrelationEntry | null) {
  if (!e) return { backgroundColor: "rgba(255,255,255,0.04)" };
  const a = Math.min(0.85, Math.abs(e.rho)) * 0.45;
  return {
    backgroundColor:
      e.rho >= 0 ? `rgba(34, 211, 238, ${a})` : `rgba(232, 121, 249, ${a})`,
  };
}

/**
 * G4 — Korelasyon paneli. Matrix heatmap + aynı yönlü cluster exposure
 * uyarıları. Correlation sizing sadece küçültür; RiskGate / DQS hard
 * gate'leri her zaman önce çalışır.
 */
export function CorrelationPanel() {
  const { data, isLoading } = useRiskCorrelation();
  if (isLoading) {
    return (
      <PanelFrame id="correlation">
        <PanelHeader title="Korelasyon" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const { symbols, cell } = selectMatrixGrid(data);
  const clusters = selectClusters(data);
  const insufficient = selectInsufficientPairs(data);
  const { threshold, maxClusterPct, windowDays } = selectLimits(data);

  if (!symbols.length) {
    return (
      <PanelFrame id="correlation">
        <PanelHeader title="Korelasyon" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="correlation">
      <PanelHeader
        title="Korelasyon"
        subtitle={`|ρ| ≥ ${fmtNum(threshold, 1)} aynı cluster · cap ${fmtPct(maxClusterPct, 0)}`}
        actions={
          <span className="text-[10px] uppercase tracking-widest text-white/40">
            sadece küçültür · RiskGate önce
          </span>
        }
      />
      <table className="text-[10px] tabular-nums border-separate border-spacing-0.5">
        <thead>
          <tr>
            <th />
            {symbols.map((s) => (
              <th key={s} className="px-1 font-normal text-white/40">
                {s.replace("USD", "")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((a) => (
            <tr key={a}>
              <td className="pr-1 text-white/40">{a.replace("USD", "")}</td>
              {symbols.map((b) => {
                const e = a === b ? null : cell(a, b);
                return (
                  <td
                    key={b}
                    className="h-7 w-9 rounded text-center text-white/80"
                    style={a === b ? { backgroundColor: "rgba(255,255,255,0.10)" } : cellStyle(e)}
                    title={e ? `${a}↔${b} ρ=${e.rho} (${e.source})` : a === b ? "1.0" : "veri yok"}
                  >
                    {a === b ? "1" : e ? fmtNum(e.rho, 2) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 space-y-1.5 text-xs">
        {clusters.length === 0 ? (
          <p className="text-white/40">Açık pozisyon cluster'ı yok.</p>
        ) : (
          clusters.map((c) => (
            <div
              key={c.symbols.join("|")}
              className="flex items-center justify-between gap-2 border-b border-white/5 pb-1"
            >
              <span className="text-white/70 truncate">{c.symbols.join(" + ")}</span>
              <span className="tabular-nums text-white/50">
                {fmtPct(c.cluster_pct, 1)} / {fmtPct(maxClusterPct, 0)}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${CLUSTER_TONE[c.status]}`}
              >
                {c.status}
              </span>
            </div>
          ))
        )}
      </div>
      {insufficient.length > 0 ? (
        <p className="mt-2 text-[11px] text-white/40">
          Yetersiz veri (neutral fallback, adjustment yok):{" "}
          {insufficient.join(", ")}
        </p>
      ) : null}
      <p className="mt-1 text-[10px] uppercase tracking-widest text-white/30">
        {windowDays}g PnL penceresi · baseline config fallback
      </p>
    </PanelFrame>
  );
}
