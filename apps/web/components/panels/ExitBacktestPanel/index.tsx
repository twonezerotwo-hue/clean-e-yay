"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useExitBacktest } from "@/lib/queries/hooks";
import type { ExitBacktestView } from "@/types/uncontracted";

// Çıkış stop-verim backtest'i (SALT-ANALİZ). Gerçek fiyat geçmişinde binlerce
// işlem simüle edilir: sabit stop ne kadar geniş, trailing ne kadar sık/erken
// olmalı ki en çok kâr yakalansın? Canlı çıkışa DOKUNMAZ — owner çıkış ayarını
// bu kanıta bakarak gözden geçirir. Panel HESAP YAPMAZ; /learning/exit-backtest.

// Bir marjinal tabloyu en iyi→kötü sırala, en verimli değeri vurgula.
function MarginalRow({ label, data, suffix }: {
  label: string;
  data: Record<string, number> | undefined;
  suffix?: string;
}) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return null;
  const best = Math.max(...entries.map(([, v]) => v));
  return (
    <div className="flex items-baseline gap-1.5 py-0.5">
      <span className="w-24 shrink-0 text-[10px] text-white/45">{label}</span>
      <div className="flex flex-wrap gap-1">
        {entries.map(([k, v]) => (
          <span
            key={k}
            className={`rounded px-1 py-0.5 text-[9px] font-mono ${
              v === best
                ? "bg-signal-up/20 text-signal-up font-bold"
                : "bg-white/5 text-white/50"
            }`}
          >
            {k}
            {suffix}: {v >= 0 ? "+" : ""}
            {v.toFixed(3)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ExitBacktestPanel() {
  const { data, isLoading } = useExitBacktest();

  if (isLoading) {
    return (
      <PanelFrame id="exit_backtest">
        <PanelHeader title="Çıkış Verim Backtest" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: ExitBacktestView | undefined = data;
  const best = d?.best_configs?.[0];

  return (
    <PanelFrame id="exit_backtest">
      <PanelHeader
        title="Çıkış Verim Backtest"
        subtitle="En verimli sabit + trailing stop aralığı (gerçek fiyat geçmişi)"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            salt-analiz
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          <div className="mb-2 text-[10px] text-white/40">
            {d.entry_count} simüle işlem · TF: {Object.entries(d.tf_counts).map(([k, v]) => `${k}=${v}`).join(" · ")}
          </div>

          {best ? (
            <div className="mb-2 rounded border border-signal-up/25 bg-signal-up/[0.06] px-2 py-1.5 text-[11px] leading-4 text-white/80">
              <span className="font-bold text-signal-up/90">En verimli config:</span>{" "}
              sabit stop <b>{best.sl_mult}R</b> · trailing <b>{best.trail_dist}R</b> mesafe,{" "}
              <b>{best.trail_act}R</b>'de devreye · partial_tp{" "}
              {best.ptp_trigger ? `${best.ptp_trigger}R/${Math.round(best.ptp_frac * 100)}%` : "KAPALI"}{" "}
              → <b>{best.avg_r >= 0 ? "+" : ""}{best.avg_r.toFixed(3)} R/işlem</b> (kazanç %{Math.round(best.win_rate * 100)})
            </div>
          ) : null}

          <div className="mb-2">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-white/40">
              En verimli aralık (marjinal, R/işlem)
            </div>
            <MarginalRow label="Sabit stop" data={d.marginal.sl_mult} suffix="R" />
            <MarginalRow label="Trailing devreye" data={d.marginal.trail_act} suffix="R" />
            <MarginalRow label="Trailing mesafe" data={d.marginal.trail_dist} suffix="R" />
            <MarginalRow label="partial_tp" data={d.marginal.ptp} />
          </div>

          {Object.keys(d.per_tf_best).length ? (
            <div className="overflow-x-auto">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-white/40">
                TF başına en verimli
              </div>
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-left text-white/40">
                    <th className="py-0.5 pr-2 font-medium">TF</th>
                    <th className="py-0.5 pr-2 text-right font-medium">Sabit SL</th>
                    <th className="py-0.5 pr-2 text-right font-medium">Trail mesafe</th>
                    <th className="py-0.5 text-right font-medium">R/işlem</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(d.per_tf_best).map(([tf, b]) => (
                    <tr key={tf} className="border-t border-white/5">
                      <td className="py-0.5 pr-2 font-mono text-white/70">{tf}</td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{b.sl_mult}R</td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{b.trail_dist}R</td>
                      <td
                        className={`py-0.5 text-right font-mono ${
                          b.avg_r >= 0 ? "text-signal-up/80" : "text-signal-down/80"
                        }`}
                      >
                        {b.avg_r >= 0 ? "+" : ""}
                        {b.avg_r.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            Salt-analiz — canlı çıkış davranışı değişmez. Bulgu tutarlıysa çıkış
            ayarı (trail mesafesi/SL) owner kararıyla ayrı güncellenir.
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Backtest henüz üretilmedi. Öğrenme döngüsü (haftalık ağır adım) çalışınca
          en verimli stop aralığı burada görünecek.
        </div>
      )}
    </PanelFrame>
  );
}
