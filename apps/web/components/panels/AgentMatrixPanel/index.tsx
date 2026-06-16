"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useAgentMatrix } from "@/lib/queries/hooks";
import {
  AGENT_TF_ORDER,
  ACTION_LABEL,
  ALIGNMENT_TONE,
  actionTone,
  biasFor,
  biasGlyph,
  biasTone,
  economicsSummary,
  isRiskRestrictive,
  patternLabel,
  reversalGlyph,
  reversalTone,
  selectAgentRows,
} from "@/lib/selectors/agent-matrix";
import type { AgentMatrixRow } from "@/types/generated/api";

// T2 step 7 — multi-TF agent pipeline yüzeyi: consensus (per-TF bias + hizalama)
// → AgentDecision (aksiyon + entry TF + ×size) → cost/R:R ekonomi kapısı. Tüm
// değerler backend ViewModel'inden gelir; frontend hesap yapmaz. EVIDENCE-only:
// panel trade açmaz; RiskGate finaldir, üst TF yalnız scale-down.

function decisionTitle(row: AgentMatrixRow): string {
  const d = row.decision;
  const c = row.consensus;
  const lines = [
    `${row.symbol} · stance ${row.stance}`,
    `karar: ${d.action}${d.entry_timeframe ? ` @ ${d.entry_timeframe}` : ""} · ×${d.size_multiplier ?? 0}`,
    `güven ${(d.confidence ?? 0).toFixed(2)} · hizalama ${c.alignment_status} (${Math.round(c.alignment_score ?? 0)}) · uyum ${Math.round(c.agreement_score ?? 0)}`,
  ];
  if (c.is_countertrend) lines.push("⚠ countertrend (asla otomatik full giriş)");
  if (d.manual_ready_required) lines.push("manual-ready gerekli");
  if (d.required_confirmations?.length)
    lines.push(`bekleyen: ${d.required_confirmations.join(", ")}`);
  if (d.reason) lines.push(d.reason);
  return lines.join("\n");
}

function AgentRow({ row, suspended }: { row: AgentMatrixRow; suspended: boolean }) {
  const d = row.decision;
  const c = row.consensus;
  return (
    <tr className="border-t border-white/5">
      <td className="p-1 font-medium">{row.symbol}</td>
      {AGENT_TF_ORDER.map((tf) => {
        const bias = biasFor(row, tf);
        return (
          <td key={tf} className="p-1">
            <div
              className={`rounded border px-1 py-0.5 text-center text-[11px] leading-none ${biasTone(bias)}`}
              title={`${tf}: ${bias ?? "—"}`}
            >
              {biasGlyph(bias)}
            </div>
          </td>
        );
      })}
      <td className="p-1 text-center">
        <span className={`text-[10px] font-medium ${ALIGNMENT_TONE[c.alignment_status ?? ""] ?? "text-white/50"}`}>
          {c.alignment_status ?? "—"}
        </span>
        <div className="text-[9px] tabular-nums text-white/40">
          {Math.round(c.alignment_score ?? 0)}/{Math.round(c.agreement_score ?? 0)}
        </div>
      </td>
      <td className="p-1">
        <div
          className={`rounded border px-1.5 py-1 text-center text-[10px] leading-tight ${
            suspended ? "border-white/10 text-white/45" : actionTone(d.action)
          }`}
          title={decisionTitle(row)}
        >
          <div className="font-medium tracking-wide">
            {ACTION_LABEL[d.action] ?? d.action}
            {d.entry_timeframe ? (
              <span className="opacity-70"> @{d.entry_timeframe}</span>
            ) : null}
          </div>
          <div className="text-[9px] tabular-nums opacity-75">
            ×{d.size_multiplier ?? 0} · {(d.confidence ?? 0).toFixed(2)}
            {c.is_countertrend ? " · CT" : ""}
          </div>
        </div>
      </td>
      <td className="p-1 text-center text-[10px] tabular-nums text-white/55">
        {economicsSummary(row)}
      </td>
      <td
        className="p-1 text-center text-[10px] leading-tight"
        title={`§4.5 evidence · pattern ${row.pattern ?? "—"} · reversal ${row.reversal_bias ?? "—"}`}
      >
        <div className="text-white/55">{patternLabel(row.pattern)}</div>
        <div className={`text-[9px] ${reversalTone(row.reversal_bias)}`}>
          {reversalGlyph(row.reversal_bias)}
        </div>
      </td>
    </tr>
  );
}

export function AgentMatrixPanel() {
  const { data, isLoading } = useAgentMatrix();
  if (isLoading) {
    return (
      <PanelFrame id="agent_matrix">
        <PanelHeader title="Agent Matrisi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const rows = selectAgentRows(data);
  if (!rows.length) {
    return (
      <PanelFrame id="agent_matrix">
        <PanelHeader title="Agent Matrisi" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const suspended = isRiskRestrictive(data?.risk_action);
  return (
    <PanelFrame id="agent_matrix">
      <PanelHeader
        title="Agent Matrisi"
        subtitle="multi-TF consensus → karar → cost/R:R"
        actions={
          suspended ? (
            <span className="rounded px-1.5 py-0.5 bg-signal-down/20 text-signal-down uppercase tracking-wide text-[10px]">
              {data?.risk_action}
            </span>
          ) : undefined
        }
      />
      {suspended ? (
        <p className="mb-2 rounded border border-signal-down/30 bg-signal-down/10 px-2 py-1 text-[11px] text-signal-down/90">
          ⛔ Global RiskGate: {data?.risk_action} — yeni giriş yok (her TF&apos;te
          finaldir; üst TF yalnız scale-down).
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[26rem] border-collapse text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-widest text-white/40">
              <th className="p-1 text-left font-normal">Sembol</th>
              {AGENT_TF_ORDER.map((tf) => (
                <th key={tf} className="p-1 font-normal">{tf}</th>
              ))}
              <th className="p-1 font-normal">Hizalama</th>
              <th className="p-1 font-normal">Karar</th>
              <th className="p-1 font-normal">Ekonomi</th>
              <th className="p-1 font-normal">Yapı</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <AgentRow key={r.symbol} row={r} suspended={suspended} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] text-white/35">
        per-TF bias (▲/▼/·) → hizalama (NEUTRAL seyreltir) → AgentDecision
        (SCOUT/CONFIRM/WATCH…) · cost+R:R kapısı SCOUT&apos;u WATCH&apos;a düşürebilir
        · CT = countertrend (asla otomatik full giriş) · RiskGate finaldir.
      </p>
    </PanelFrame>
  );
}
