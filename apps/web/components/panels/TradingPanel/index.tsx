"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { SparkLine } from "@/components/charts/SparkLine";
import {
  usePaperTradingState,
  useRiskCorrelation,
  useRiskHalts,
} from "@/lib/queries/hooks";
import { selectFlaggedClusters, selectLimits } from "@/lib/selectors/correlation";
import { selectHaltLevel } from "@/lib/selectors/halts";
import { fmtUSD, fmtPct, fmtNum, fmtRelative } from "@/lib/format";
import type { Position } from "@/types/generated/api";

// T2 — açık pozisyon satırı: TF rozeti + time-stop (valid_until).
function OpenPositions({ positions }: { positions: Position[] }) {
  if (!positions.length) return null;
  return (
    <ul className="mt-3 space-y-1 text-[11px]">
      {positions.map((p) => (
        <li
          key={p.id}
          className="flex items-center justify-between border-b border-white/5 pb-0.5"
        >
          <span className="flex items-center gap-1.5">
            <span className="font-medium">{p.symbol}</span>
            <span className="rounded border border-accent-cyan/40 px-1 py-px text-[9px] uppercase text-accent-cyan">
              {p.timeframe ?? "1d"}
            </span>
            <span
              className={
                p.side === "long" ? "text-signal-up" : "text-signal-down"
              }
            >
              {p.side}
            </span>
          </span>
          {/* UX1 — time-stop durumu backend'de; negatif/yanıltıcı geri sayım YOK. */}
          <span className="tabular-nums">
            {(p.time_stop_status ?? (p.valid_until ? "ACTIVE" : "NONE")) ===
            "EXPIRED" ? (
              <span className="text-amber-400">TIME_STOP_EXPIRED</span>
            ) : p.valid_until ? (
              <span className="text-white/45">time-stop {fmtRelative(p.valid_until)}</span>
            ) : (
              <span className="text-white/45">time-stop yok</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function TradingPanel() {
  const { data, isLoading } = usePaperTradingState();
  const { data: corr } = useRiskCorrelation();
  const { data: halts } = useRiskHalts();
  const haltLevel = selectHaltLevel(halts);
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
        actions={
          haltLevel ? (
            <span
              className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
                haltLevel === "KILL_SWITCH"
                  ? "bg-signal-down/20 text-signal-down"
                  : "bg-amber-400/20 text-amber-400"
              }`}
            >
              RISK FREEZE · {haltLevel}
            </span>
          ) : undefined
        }
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
      <OpenPositions positions={data.open_positions} />
      <ClusterExposure corr={corr} />
    </PanelFrame>
  );
}

/** G4 — aynı yönlü korelasyonlu cluster exposure (backend hesaplar). */
function ClusterExposure({
  corr,
}: {
  corr: Parameters<typeof selectFlaggedClusters>[0];
}) {
  const flagged = selectFlaggedClusters(corr);
  if (!flagged.length) return null;
  const { maxClusterPct } = selectLimits(corr);
  return (
    <div className="mt-2 space-y-1 text-[11px]">
      {flagged.map((c) => (
        <div
          key={c.symbols.join("|")}
          className={
            c.status === "BREACH" ? "text-signal-down" : "text-amber-400"
          }
        >
          cluster {c.symbols.join("+")} · {fmtPct(c.cluster_pct, 1)} /{" "}
          {fmtPct(maxClusterPct, 0)} · {c.status}
        </div>
      ))}
    </div>
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
