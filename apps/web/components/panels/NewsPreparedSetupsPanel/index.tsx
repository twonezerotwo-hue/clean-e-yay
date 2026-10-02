"use client";

import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
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

export function NewsPreparedSetupsPanel() {
  const { data, isLoading } = useCockpitBrief();
  const setups = (data?.news_prepared_setups ?? [])
    .filter((setup) => ["WAITING_RISK", "ARMED", "ACTIVATED"].includes(setup.status))
    .slice()
    .reverse();
  const waiting = setups.filter((setup) => setup.status === "WAITING_RISK").length;

  return (
    <PanelFrame id="news_prepared_setups" className="border-accent-cyan/20">
      <PanelHeader
        title="Haber Kaynaklı Hazır Pozisyonlar"
        subtitle="haber → öngörü → RiskGate sonrası otomatik yeniden değerlendirme"
        actions={
          <span className="rounded border border-amber-300/20 bg-amber-300/8 px-2 py-1 text-[10px] uppercase tracking-widest text-amber-200/80">
            {waiting} risk bekliyor
          </span>
        }
      />
      {isLoading ? <LoadingState /> : !setups.length ? (
        <EmptyState message="Doğrulanmış haber kaynaklı hazır pozisyon yok." />
      ) : (
        <div className="space-y-2">
          <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs leading-5 text-white/55">
            Bu kayıtlar emir değildir. Geçerlilik süresi içinde mevcut teknik, seans ve RiskGate zinciri izin verirse paper pozisyonuna dönüşür.
          </div>
          {setups.slice(0, 8).map((setup: NewsPreparedSetup) => (
            <div key={setup.id} className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-sm text-white/90">
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
      )}
    </PanelFrame>
  );
}
