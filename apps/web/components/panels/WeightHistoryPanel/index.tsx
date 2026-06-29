"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useRebalanceProposal } from "@/lib/queries/hooks";
import {
  selectActiveVersion,
  selectAutoApplyActive,
  selectAutoApplyLedger,
  selectHistory,
} from "@/lib/selectors/rebalance";
import { fmtRelative } from "@/lib/format";
import type { WeightAutoApplyEntry } from "@/types/generated/api";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "bg-amber-400/20 text-amber-400",
  APPROVED: "bg-signal-up/20 text-signal-up",
  REJECTED: "bg-signal-down/20 text-signal-down",
  AUTO_APPLIED: "bg-indigo-400/20 text-indigo-300",
};

const fmtExp = (v: number | undefined): string =>
  typeof v === "number" ? v.toFixed(1) : "—";

type HistoryItems = ReturnType<typeof selectHistory>;

export function WeightHistoryPanel() {
  const { data, isLoading } = useRebalanceProposal();
  if (isLoading) {
    return (
      <PanelFrame id="weight_history">
        <PanelHeader title="Ağırlık Geçmişi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const items = selectHistory(data);
  const active = selectActiveVersion(data);
  const autoActive = selectAutoApplyActive(data);
  const autoLedger = selectAutoApplyLedger(data);
  const visible = items.slice(0, 5);
  const hidden = items.slice(5);
  const rejected = items.filter((h) => h.status === "REJECTED").length;
  const approved = items.filter((h) => h.status === "APPROVED").length;

  if (!items.length && !autoActive && !autoLedger.length) {
    return (
      <PanelFrame id="weight_history">
        <PanelHeader title="Ağırlık Geçmişi" subtitle={`aktif v${active}`} />
        <EmptyState />
      </PanelFrame>
    );
  }

  return (
    <PanelFrame id="weight_history">
      <PanelHeader
        title="Ağırlık Geçmişi"
        subtitle={`aktif v${active} · ${items.length} kayıt · ${approved} onay / ${rejected} red`}
      />
      <AutoApplyBlock active={autoActive} ledger={autoLedger} />
      <HistoryList items={visible} />
      {hidden.length ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-white/35">
            {hidden.length} eski kaydı göster
          </summary>
          <div className="mt-1">
            <HistoryList items={hidden} startIndex={visible.length} />
          </div>
        </details>
      ) : null}
    </PanelFrame>
  );
}

// G3 — otomatik-uygulama görünürlüğü: izlenen aktif apply + onay/geri-alış olayları.
// Owner, ağırlıkların ne zaman kendi başına değişip geri alındığını burada görür.
function AutoApplyBlock({
  active,
  ledger,
}: {
  active: WeightAutoApplyEntry | null;
  ledger: WeightAutoApplyEntry[];
}) {
  const events = ledger
    .filter((e) => e.event === "CONFIRMED" || e.event === "ROLLED_BACK")
    .slice(0, 3);
  if (!active && !events.length) return null;
  return (
    <div className="mb-2 rounded border border-white/5 bg-white/[0.02] p-2">
      <div className="mb-1 text-[10px] uppercase tracking-widest text-white/35">
        otomatik uygulama
      </div>
      {active ? (
        <div className="flex items-center gap-2 text-[11px]">
          <span className="rounded bg-indigo-400/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-indigo-300">
            izleniyor
          </span>
          <span className="tabular-nums text-white/75">v{active.applied_version}</span>
          <span className="text-white/35">baseline {fmtExp(active.baseline_expectancy)}</span>
          <span className="ml-auto text-white/40">{fmtRelative(active.applied_at)}</span>
        </div>
      ) : null}
      {events.length ? (
        <ul className="mt-1 space-y-0.5 text-[11px]">
          {events.map((e, i) => {
            const rolled = e.event === "ROLLED_BACK";
            return (
              <li
                key={`${e.applied_version}-${i}`}
                className="flex items-center gap-2"
              >
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                    rolled
                      ? "bg-signal-down/20 text-signal-down"
                      : "bg-signal-up/20 text-signal-up"
                  }`}
                >
                  {rolled ? "geri alındı" : "onaylandı"}
                </span>
                <span className="tabular-nums text-white/70">v{e.applied_version}</span>
                <span className="text-white/35">
                  sonuç {fmtExp(e.post_expectancy)} / baseline {fmtExp(e.baseline_expectancy)}
                </span>
                <span className="ml-auto text-white/40">{fmtRelative(e.resolved_at)}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function HistoryList({
  items,
  startIndex = 0,
}: {
  items: HistoryItems;
  startIndex?: number;
}) {
  return (
    <ul className="space-y-1 text-[11px]">
      {items.map((h, i) => {
        const changed = (h.deltas ?? []).filter((d) => Math.abs(d.delta) >= 0.0001);
        const summary = changed.length ? `${changed.length} değişim` : "değişim yok";
        return (
          <li
            key={`${h.to_version}-${startIndex + i}`}
            className="grid grid-cols-[1fr_auto] items-center gap-2 border-b border-white/5 pb-1"
          >
            <span className="min-w-0">
              <span className="font-medium tabular-nums text-white/75">
                v{h.from_version} → v{h.to_version}
              </span>
              <span className="ml-2 text-white/35">{h.regime}</span>
              <span className="ml-2 text-white/30">{summary}</span>
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                  STATUS_COLOR[h.status] ?? "bg-white/10 text-white/40"
                }`}
              >
                {h.status}
              </span>
              <span className="text-white/40">{fmtRelative(h.generated_at)}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
