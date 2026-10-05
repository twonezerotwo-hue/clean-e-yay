"use client";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCockpitBrief } from "@/lib/queries/hooks";
import type { NewsPreparedSetup } from "@/types/generated/api";

function statusLabel(status: string) {
  if (status === "WAITING_RISK") return "Risk bekliyor";
  if (status === "ARMED") return "Hazır / yeniden değerlendirilecek";
  if (status === "ACTIVATED") return "Açıldı";
  if (status === "EXPIRED") return "Süresi doldu";
  return status;
}

function statusTone(status: string) {
  if (status === "ACTIVATED") return "text-emerald-300";
  if (status === "WAITING_RISK") return "text-amber-300";
  if (status === "ARMED") return "text-cyan-300";
  return "text-white/45";
}

function pct(value?: number | null) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function price(value?: number | null) {
  return value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

/** Haber kaynaklı hazır pozisyonlar — Fikirler panelinin içinde katlanır bölüm (owner kararı 2026-10-05). */
export function NewsPreparedSetupsSection() {
  const { data, isLoading } = useCockpitBrief();
  const setups = (data?.news_prepared_setups ?? [])
    .filter((setup) => ["WAITING_RISK", "ARMED", "ACTIVATED"].includes(setup.status))
    .slice()
    .reverse();

  if (isLoading) return <LoadingState />;
  if (!setups.length) return <EmptyState message="Doğrulanmış haber kaynaklı hazır pozisyon yok." />;
  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-[11px] leading-5 text-white/55">
        Emir değildir. Yön dünya-durumu gölge tahmininden gelir; aynı yönde bir paper pozisyon kanonik karar
        zincirinde (teknik, seans, RiskGate) açılırsa &quot;Açıldı&quot; olarak işaretlenir.
      </div>
      {setups.slice(0, 8).map((setup: NewsPreparedSetup) => (
        <div key={setup.id} className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-mono text-xs text-white/90">
                {setup.symbol} · {setup.timeframe} · {setup.side.toUpperCase()}
              </div>
              <div className="mt-1 text-[10px] text-white/42">{setup.news_title ?? setup.event_type ?? "Dünya olayı"}</div>
            </div>
            <div className={`text-right text-[10px] font-semibold uppercase tracking-widest ${statusTone(setup.status)}`}>
              {statusLabel(setup.status)}
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-white/55 sm:grid-cols-4">
            <div><span className="text-white/35">Güven </span>{pct(setup.confidence)}</div>
            <div><span className="text-white/35">Yön skoru </span>{setup.world_score == null ? "—" : setup.world_score.toFixed(1)}</div>
            <div><span className="text-white/35">Fiyat </span>{price(setup.current_price)}</div>
            <div><span className="text-white/35">Bant p50 </span>{price(setup.p50)}</div>
          </div>
          {setup.last_blocker ? <div className="mt-1 text-[10px] text-amber-200/65">Bekleme nedeni: {setup.last_blocker}</div> : null}
        </div>
      ))}
    </div>
  );
}
