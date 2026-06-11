"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useDataSnapshot } from "@/lib/queries/hooks";
import { selectPrices } from "@/lib/selectors/snapshot";
import { fmtNum } from "@/lib/format";

const SOURCE_COLOR: Record<string, string> = {
  coingecko: "text-accent-cyan",
  yfinance: "text-accent-magenta",
  fred: "text-accent-lime",
  mock: "text-amber-400",
  none: "text-white/40",
};

export function MarketDataPanel() {
  const { data, isLoading } = useDataSnapshot();
  if (isLoading) {
    return (
      <PanelFrame id="market_data">
        <PanelHeader title="Piyasa Verisi" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const prices = selectPrices(data);
  if (!prices.length) {
    return (
      <PanelFrame id="market_data">
        <PanelHeader title="Piyasa Verisi" />
        <EmptyState />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="market_data">
      <PanelHeader
        title="Piyasa Verisi"
        subtitle={`${prices.length} sembol`}
      />
      <ul className="space-y-1.5 text-sm">
        {prices.map((p) => {
          const isUnavailable = p.price == null || p.status === "DATA_UNAVAILABLE";
          return (
            <li
              key={p.symbol}
              className="flex items-center justify-between border-b border-white/5 pb-1"
            >
              <span className="font-medium">{p.symbol}</span>
              <span className="flex items-center gap-3 text-xs">
                {isUnavailable ? (
                  <span
                    className="rounded px-1.5 py-0.5 bg-signal-down/20 text-signal-down uppercase tracking-wide text-[10px]"
                    title={p.error ?? undefined}
                  >
                    VERİ YOK
                  </span>
                ) : (
                  <>
                    <span className="text-white/80 tabular-nums">
                      {fmtNum(p.price, 2)}
                    </span>
                    <span
                      className={`uppercase tracking-wide text-[10px] ${
                        SOURCE_COLOR[p.source] ?? "text-white/40"
                      }`}
                    >
                      {p.source}
                    </span>
                    {p.status === "MOCK" ? (
                      <span className="rounded px-1 py-0.5 bg-amber-400/20 text-amber-400 text-[10px]">
                        MOCK
                      </span>
                    ) : null}
                    {!p.verified && p.status !== "MOCK" ? (
                      <span className="rounded px-1 py-0.5 bg-signal-down/20 text-signal-down text-[10px]">
                        unverified
                      </span>
                    ) : null}
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </PanelFrame>
  );
}
