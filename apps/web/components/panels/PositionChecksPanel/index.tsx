"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { usePaperTradingState } from "@/lib/queries/hooks";
import { fmtUSD, fmtNum } from "@/lib/format";
import type { PositionRecheck, PositionRecheckVerdict } from "@/types/generated/api";

const VERDICT_BADGE: Record<PositionRecheckVerdict, string> = {
  OK:             "border-emerald-700/50 text-emerald-300/90",
  WATCH:          "border-amber-700/50 text-amber-300/90",
  REDUCE:         "border-orange-700/60 text-orange-300",
  EXIT_RECOMMEND: "border-red-700/60 text-red-300",
};

const VERDICT_LABEL: Record<PositionRecheckVerdict, string> = {
  OK:             "OK",
  WATCH:          "İZLE",
  REDUCE:         "AZALT",
  EXIT_RECOMMEND: "ÇIK",
};

function VerdictBadge({ r }: { r: PositionRecheck | undefined }) {
  if (!r) {
    return <span className="text-white/30">—</span>;
  }
  return (
    <span
      className={`inline-block rounded border px-1.5 py-px text-[10px] font-mono uppercase tracking-widest ${VERDICT_BADGE[r.verdict]}`}
      title={r.reason}
    >
      {VERDICT_LABEL[r.verdict]}
    </span>
  );
}

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
  const rechecks = data.position_rechecks ?? [];
  const byPos = new Map<string, PositionRecheck>(rechecks.map((r) => [r.position_id, r]));
  const alerts = rechecks.filter((r) => r.verdict === "REDUCE" || r.verdict === "EXIT_RECOMMEND").length;
  return (
    <PanelFrame id="position_checks">
      <PanelHeader
        title="Pozisyon Kontrolleri"
        subtitle={
          alerts > 0
            ? `${data.open_positions.length} açık · ${alerts} öneri`
            : `${data.open_positions.length} açık`
        }
      />
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
              <th className="text-center">Karar</th>
            </tr>
          </thead>
          <tbody>
            {data.open_positions.map((p) => {
              const r = byPos.get(p.id);
              return (
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
                  <td className="text-center">
                    <VerdictBadge r={r} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rechecks.length === 0 ? (
        <p className="mt-2 text-[10px] font-mono text-white/35">
          Henüz tick atılmadı — recheck verdict'leri ilk tick'te oluşur.
        </p>
      ) : (
        <p className="mt-2 text-[10px] font-mono text-white/30">
          Recheck önerisi (otomatik kapatma yok) · son: {data.last_recheck_at?.slice(11, 19) ?? "—"}
        </p>
      )}
    </PanelFrame>
  );
}
