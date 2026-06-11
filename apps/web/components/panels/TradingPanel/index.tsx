"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { SparkLine } from "@/components/charts/SparkLine";
import { usePaperTradingState } from "@/lib/queries/hooks";
import { fmtUSD, fmtPct, fmtNum } from "@/lib/format";

export function TradingPanel() {
  const { data, isLoading } = usePaperTradingState();
  if (isLoading) {
    return (
      <PanelFrame id="trading">
        <PanelHeader title="Paper Trading" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data) {
    return (
      <PanelFrame id="trading">
        <PanelHeader title="Paper Trading" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const equityCurve = (data.recent_trades ?? []).map((t) => t.pnl_usd).reduce<number[]>(
    (acc, p) => {
      const last = acc.at(-1) ?? data.equity_usd - data.realized_pnl_usd;
      acc.push(last + p);
      return acc;
    },
    [],
  );
  const pnlPositive = data.realized_pnl_usd >= 0;
  return (
    <PanelFrame id="trading">
      <PanelHeader
        title="Paper Trading"
        subtitle={`${data.open_positions.length} açık · ${data.recent_trades.length} kapanmış`}
      />
      <div className="grid grid-cols-3 gap-3 text-xs mb-3">
        <Stat label="Equity" value={fmtUSD(data.equity_usd)} />
        <Stat
          label="Realized"
          value={fmtUSD(data.realized_pnl_usd)}
          className={pnlPositive ? "text-signal-up" : "text-signal-down"}
        />
        <Stat label="Max DD" value={fmtPct(data.max_drawdown_pct)} />
      </div>
      <div className={pnlPositive ? "text-signal-up" : "text-signal-down"}>
        <SparkLine data={equityCurve} width={320} height={56} />
      </div>
      <div className="text-[10px] uppercase tracking-widest text-white/40 mt-2">
        Sharpe 30g: {fmtNum(data.sharpe_30d)}
      </div>
    </PanelFrame>
  );
}

function Stat({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-white/40">{label}</div>
      <div className={`text-sm ${className || "text-white/90"}`}>{value}</div>
    </div>
  );
}
