"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useLearningSummary } from "@/lib/queries/hooks";
import { fmtNum, fmtPct } from "@/lib/format";
import type { OutcomeBucket } from "@/types/generated/api";

type BucketMap = Record<string, OutcomeBucket> | undefined;

const ROW_LIMIT = 6;

function rowsFrom(map: BucketMap) {
  return Object.entries(map ?? {})
    .sort(([, a], [, b]) => b.trades - a.trades)
    .slice(0, ROW_LIMIT);
}

function pnlTone(value: number) {
  if (value > 0) return "text-signal-up";
  if (value < 0) return "text-signal-down";
  return "text-white/50";
}

function BucketGroup({ title, data }: { title: string; data: BucketMap }) {
  const rows = rowsFrom(data);
  return (
    <section className="min-w-0">
      <div className="mb-1 text-[10px] uppercase tracking-widest text-white/40">
        {title}
      </div>
      {!rows.length ? (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/35">
          Kayit yok
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[18rem] border-collapse text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-white/35">
                <th className="p-1 text-left font-normal">Key</th>
                <th className="p-1 font-normal">N</th>
                <th className="p-1 font-normal">Win</th>
                <th className="p-1 text-right font-normal">PnL</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([key, b]) => (
                <tr key={key} className="border-t border-white/5">
                  <td className="max-w-[9rem] truncate p-1 font-medium uppercase tracking-wide text-white/75">
                    {key || "unknown"}
                  </td>
                  <td className="p-1 text-center tabular-nums text-white/60">
                    {b.trades}
                  </td>
                  <td className="p-1 text-center tabular-nums text-white/70">
                    {fmtPct(b.win_rate, 0)}
                  </td>
                  <td className={`p-1 text-right tabular-nums ${pnlTone(b.total_pnl)}`}>
                    {fmtNum(b.total_pnl, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function OutcomeLedgerPanel() {
  const { data, isLoading } = useLearningSummary();

  if (isLoading) {
    return (
      <PanelFrame id="outcome_ledger">
        <PanelHeader title="İşlem Sonuç Defteri" />
        <LoadingState />
      </PanelFrame>
    );
  }

  if (!data) {
    return (
      <PanelFrame id="outcome_ledger">
        <PanelHeader title="İşlem Sonuç Defteri" />
        <EmptyState />
      </PanelFrame>
    );
  }

  const outcomes = data.outcomes_total ?? data.total_trades;
  const verified = data.verified_outcomes ?? data.total_trades;

  return (
    <PanelFrame id="outcome_ledger">
      <PanelHeader
        title="İşlem Sonuç Defteri"
        subtitle={`${verified}/${outcomes} doğrulanmış işlem`}
        actions={
          <span className="rounded px-1.5 py-0.5 bg-white/10 text-[10px] uppercase tracking-widest text-white/55">
            {data.sample_sufficient === false ? "LOW SAMPLE" : "READY"}
          </span>
        }
      />

      <div className="mb-3 grid grid-cols-4 gap-2 text-xs">
        <Stat label="Recent" value={String(data.total_trades)} />
        <Stat label="Outcome" value={String(outcomes)} />
        <Stat label="Verified" value={String(verified)} />
        <Stat label="Win" value={fmtPct(data.win_rate, 0)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <BucketGroup title="Timeframe" data={data.by_timeframe} />
        <BucketGroup title="Symbol" data={data.by_symbol} />
        <BucketGroup title="Regime" data={data.by_regime} />
        <BucketGroup title="Close Reason" data={data.by_close_reason} />
        <div className="lg:col-span-2">
          <BucketGroup title="Dominant Module" data={data.by_dominant_module} />
        </div>
      </div>
    </PanelFrame>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-white/10 bg-white/[0.025] px-2 py-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className="mt-1 font-display text-lg leading-none tabular-nums text-white/86">
        {value}
      </div>
    </div>
  );
}
