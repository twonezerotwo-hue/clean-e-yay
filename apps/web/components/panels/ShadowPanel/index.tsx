"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useShadowComparison } from "@/lib/queries/hooks";
import {
  AGREEMENT_LABEL,
  agreementChips,
  agreementTone,
  dirGlyph,
  selectShadowRows,
  trustSummary,
} from "@/lib/selectors/shadow";
import type { ShadowRow } from "@/types/generated/api";

// Step 9 — controlled activation (OBSERVATION mode). The NEW agent pipeline runs in
// shadow next to the live decide_matrix engine; this panel surfaces the comparison.
// affect_decision:false → the shadow NEVER moves paper (affected_paper always false).
// All values come from the backend ViewModel; frontend does no math.

function intentText(action?: string | null, dir?: string | null): string {
  if (!action) return "—";
  return `${dirGlyph(dir)} ${action}`;
}

function ShadowTableRow({ row }: { row: ShadowRow }) {
  return (
    <tr className="border-t border-white/5">
      <td className="p-1 font-medium">{row.symbol}</td>
      <td className="p-1 text-center text-[11px] tabular-nums text-white/65">
        {intentText(row.live_action, row.live_direction)}
        {row.live_timeframe ? (
          <span className="opacity-60"> @{row.live_timeframe}</span>
        ) : null}
      </td>
      <td className="p-1 text-center text-[11px] tabular-nums text-white/65">
        {intentText(row.shadow_action, row.shadow_direction)}
        {row.shadow_entry_timeframe ? (
          <span className="opacity-60"> @{row.shadow_entry_timeframe}</span>
        ) : null}
      </td>
      <td className="p-1 text-center">
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${agreementTone(row.agreement)}`}
          title={`canlı: ${row.live_action ?? "—"} · shadow: ${row.shadow_action ?? "—"}`}
        >
          {AGREEMENT_LABEL[row.agreement] ?? row.agreement}
        </span>
      </td>
    </tr>
  );
}

export function ShadowPanel() {
  const { data, isLoading } = useShadowComparison();
  if (isLoading) {
    return (
      <PanelFrame id="shadow">
        <PanelHeader title="Shadow Gözlem" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const rows = selectShadowRows(data);
  if (!data?.available || !rows.length) {
    return (
      <PanelFrame id="shadow">
        <PanelHeader title="Shadow Gözlem" subtitle="canlı vs yeni pipeline · observe-only" />
        <EmptyState message="Henüz shadow kaydı yok — worker bir tick yazınca dolar." />
      </PanelFrame>
    );
  }
  const chips = agreementChips(data);
  return (
    <PanelFrame id="shadow">
      <PanelHeader
        title="Shadow Gözlem"
        subtitle="canlı decide_matrix vs yeni agent pipeline"
        actions={
          <span className="rounded px-1.5 py-0.5 bg-accent-cyan/15 text-accent-cyan uppercase tracking-wide text-[10px]">
            observe-only
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        🛡 affect_decision: <b>false</b> — shadow paper&apos;a yazmaz (affected_paper
        her zaman false). {trustSummary(data)}.
      </p>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {chips.map((c) => (
          <span
            key={c.key}
            className={`rounded border px-1.5 py-0.5 text-[10px] tabular-nums ${agreementTone(c.key)}`}
          >
            {c.label}: {c.count}
          </span>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[24rem] border-collapse text-xs">
          <thead>
            <tr className="text-[10px] uppercase tracking-widest text-white/40">
              <th className="p-1 text-left font-normal">Sembol</th>
              <th className="p-1 font-normal">Canlı</th>
              <th className="p-1 font-normal">Shadow</th>
              <th className="p-1 font-normal">Karşılaştırma</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <ShadowTableRow key={r.symbol} row={r} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] text-white/35">
        Adım 9 controlled activation (gözlem fazı) · canlı engine kararı sürer; yeni
        pipeline yalnız izlenir. tf_weights kalibrasyon doğrulayana kadar PRIOR
        (güvenilmez) · RiskGate finaldir.
      </p>
    </PanelFrame>
  );
}
