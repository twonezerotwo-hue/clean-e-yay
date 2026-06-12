"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDecisionMatrix } from "@/lib/queries/hooks";
import {
  MATRIX_TF_ORDER,
  selectMatrixRows,
  selectMatrixSuspended,
  selectMatrixRiskGate,
  selectMatrixDqsStatus,
  selectMatrixEventRisk,
  cellBlockedLabel,
} from "@/lib/selectors/decision";
import type { TimeframeDecision } from "@/types/generated/api";

// T2 — agent brain görünürlüğü: hücre tooltip'i candidate → final,
// blocked_by, risk gate ve paper aksiyonunu gösterir. Tüm rozetler
// backend ViewModel'inden gelir; burada hesap yapılmaz.

const ACTION_LABEL: Record<string, string> = {
  open_long: "LONG",
  open_short: "SHORT",
  hold: "—",
  blocked: "✕",
  watch: "WATCH",
};

function cellTone(c: TimeframeDecision): string {
  if (c.status === "SUSPENDED") return "border-signal-down/40 text-signal-down/80 bg-signal-down/5";
  if (c.status === "ACTIONABLE")
    return c.action === "open_long"
      ? "border-signal-up/50 text-signal-up bg-signal-up/10"
      : "border-accent-magenta/50 text-accent-magenta bg-accent-magenta/10";
  return "border-white/10 text-white/45";
}

function cellTitle(c: TimeframeDecision): string {
  const lines = [
    `${c.symbol} ${c.timeframe}`,
    `candidate: ${c.candidate_action ?? "?"} → final: ${c.action}`,
    `score ${c.score ?? "—"} · ${c.direction ?? "—"} · size ×${c.size_multiplier ?? 0}`,
    `paper: ${c.paper_action ?? "none"} · ${c.status ?? ""}`,
  ];
  if (c.blocked_by?.length) lines.push(`blocked_by: ${c.blocked_by.join(", ")}`);
  if (c.reason) lines.push(c.reason);
  return lines.join("\n");
}

function MatrixCell({ c }: { c: TimeframeDecision }) {
  const candidateDiffers =
    c.candidate_action != null && c.candidate_action !== c.action;
  return (
    <td className="p-1">
      <div
        className={`rounded border px-1.5 py-1 text-center text-[10px] leading-tight ${cellTone(c)}`}
        title={cellTitle(c)}
        data-status={c.status}
      >
        <div className="font-medium tracking-wide">
          {candidateDiffers ? (
            <>
              <span className="line-through opacity-50 mr-1">
                {ACTION_LABEL[c.candidate_action!] ?? c.candidate_action}
              </span>
              {ACTION_LABEL[c.action] ?? c.action}
            </>
          ) : (
            ACTION_LABEL[c.action] ?? c.action
          )}
        </div>
        <div className="tabular-nums opacity-80">{Math.round(c.score ?? 0)}</div>
        <div className="text-[8px] uppercase tracking-wider opacity-70">
          {c.status === "SUSPENDED"
            ? "SUSPENDED"
            : c.actionable
              ? "ACTIONABLE"
              : "NOT ACT."}
        </div>
        {/* P0/T2 — bir hücreyi hangi kapı kıstı (event riski, risk gate,
            mistake, korelasyon, 1w bias) kısa rozette görünür. */}
        {cellBlockedLabel(c) ? (
          <div className="mt-0.5 truncate text-[7px] uppercase tracking-wider opacity-60">
            {cellBlockedLabel(c)}
          </div>
        ) : null}
      </div>
    </td>
  );
}

export function TimeframeMatrixPanel() {
  const { data, isLoading } = useDecisionMatrix();
  if (isLoading) {
    return (
      <PanelFrame id="timeframe_matrix">
        <PanelHeader title="Timeframe Matrisi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const rows = selectMatrixRows(data);
  if (!rows.length) {
    return (
      <PanelFrame id="timeframe_matrix">
        <PanelHeader title="Timeframe Matrisi" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const suspended = selectMatrixSuspended(data);
  const riskGate = selectMatrixRiskGate(data);
  const dqs = selectMatrixDqsStatus(data);
  const eventRisk = selectMatrixEventRisk(data);
  return (
    <PanelFrame id="timeframe_matrix">
      <PanelHeader
        title="Timeframe Matrisi"
        subtitle="symbol × TF · candidate → final"
        actions={
          suspended ? (
            <span className="rounded px-1.5 py-0.5 bg-signal-down/20 text-signal-down uppercase tracking-wide text-[10px]">
              SUSPENDED · {riskGate?.action ?? dqs}
            </span>
          ) : undefined
        }
      />
      {suspended && riskGate ? (
        <p className="mb-2 text-[11px] text-signal-down/90">
          Risk kapısı: {riskGate.action} — {riskGate.reason}. Tüm
          timeframe&apos;lerde yeni işlem yok.
        </p>
      ) : null}
      {/* P0 — olay riski yaklaşan yüksek etkili takvim olayını ve hücreleri
          neden kıstığını gösterir (RiskGate'i bypass etmez; yalnızca kısıtlar). */}
      {eventRisk && eventRisk.level !== "NONE" ? (
        <p
          className={`mb-2 text-[11px] ${
            eventRisk.restrictive ? "text-signal-down/90" : "text-amber-300/90"
          }`}
        >
          ⚑ {eventRisk.reason}
        </p>
      ) : null}
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-widest text-white/40">
            <th className="p-1 text-left font-normal">Sembol</th>
            {(data?.timeframes ?? MATRIX_TF_ORDER).map((tf) => (
              <th key={tf} className="p-1 font-normal">{tf}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="border-t border-white/5">
              <td className="p-1 font-medium">{r.symbol}</td>
              {r.cells.map((c) => (
                <MatrixCell key={c.timeframe} c={c} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-white/35">
        1w strategic — paper işlem açmaz (bias/filtre) · 15m ×0.25, 1h ×0.5
        risk çarpanı · RiskGate her TF&apos;te finaldir.
      </p>
    </PanelFrame>
  );
}
