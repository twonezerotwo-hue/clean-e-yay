"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { usePaperTradingState } from "@/lib/queries/hooks";
import { fmtUSD, fmtNum } from "@/lib/format";

export function PositionChecksPanel() {
  const { data, isLoading } = usePaperTradingState();
  if (isLoading) {
    return (
      <PanelFrame id="position_checks">
        <PanelHeader title="Pozisyon Kontrolleri" />
        <LoadingState />
      </PanelFrame>
    );
  }
  if (!data || !data.open_positions.length) {
    return (
      <PanelFrame id="position_checks">
        <PanelHeader title="Pozisyon Kontrolleri" />
        <EmptyState message="Açık pozisyon yok." />
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="position_checks">
      <PanelHeader title="Pozisyon Kontrolleri" subtitle={`${data.open_positions.length} açık`} />
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/40">
            <tr>
              <th className="text-left py-1">Sembol</th>
              <th className="text-left">Yön</th>
              <th className="text-right">Giriş</th>
              <th className="text-right">Şimdi</th>
              <th className="text-right">SL</th>
              <th className="text-right">TP</th>
              <th className="text-right">Boyut</th>
              <th className="text-right">PnL</th>
            </tr>
          </thead>
          <tbody>
            {data.open_positions.map((p) => (
              <tr key={p.id} className="border-t border-white/5">
                <td className="py-1.5 text-white/80">{p.symbol}</td>
                <td className={p.side === "long" ? "text-signal-up" : "text-signal-down"}>{p.side}</td>
                <td className="text-right">{fmtNum(p.entry_price)}</td>
                <td className="text-right">{fmtNum(p.current_price)}</td>
                <td className="text-right">{fmtNum(p.sl)}</td>
                <td className="text-right">{fmtNum(p.tp)}</td>
                <td className="text-right">{fmtUSD(p.size_usd)}</td>
                <td
                  className={`text-right ${
                    (p.unrealized_pnl_usd ?? 0) >= 0 ? "text-signal-up" : "text-signal-down"
                  }`}
                >
                  {fmtUSD(p.unrealized_pnl_usd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PanelFrame>
  );
}
