"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useExitForensics } from "@/lib/queries/hooks";
import type { ExitForensicsBucket, ExitForensicsView } from "@/types/generated/api";

// Çıkış Otopsisi (denetim 2026-07-03) — kötü çıkışın NEREDE ve tahmini KAÇA
// olduğu. Yalnız AUTO kohort (robotun kendi işlemleri); manuel/test şeffaflık
// satırında. Frontend hesap YAPMAZ; tüm sayılar /learning/exit-forensics'ten.
// MFE/MAE yalnız pozisyon açıkken kaydedilir — "stop olmasa TP'ye gider miydi"
// gibi kapanış-sonrası kurgular backend'de de YOKTUR (dürüstlük sözleşmesi).

const CATEGORY_LABEL: Record<string, string> = {
  sl: "Stop",
  tp: "Hedef",
  time_stop: "Süre doluş",
  trailing: "İz-süren stop",
  manual: "Manuel",
  other: "Diğer",
};

const KIND_CHIP: Record<string, string> = {
  TRAILING_GIVEBACK: "bg-amber-400/20 text-amber-300",
  SL_ROUNDTRIP: "bg-signal-down/20 text-signal-down",
  TIMESTOP_MISSED: "bg-sky-400/20 text-sky-300",
};

function usd(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `$${v.toFixed(0)}`;
}

function bucketCost(b: ExitForensicsBucket): number | null {
  const parts = [b.give_back_usd_est_total, b.missed_usd_est_total].filter(
    (x): x is number => x !== null && x !== undefined,
  );
  return parts.length ? parts.reduce((a, x) => a + x, 0) : null;
}

export function ExitForensicsPanel() {
  const { data, isLoading } = useExitForensics();

  if (isLoading) {
    return (
      <PanelFrame id="exit_forensics">
        <PanelHeader title="Çıkış Otopsisi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: ExitForensicsView | undefined = data;
  const buckets = (d?.buckets ?? []).filter((b) => b.n > 0);
  // Trend oku: worker snapshot kuyruğundaki son iki toplam maliyet noktası.
  const tail = (d?.history_tail ?? []) as Array<{
    total_bad_exit_cost_usd_est?: number | null;
  }>;
  const prevCost = tail.length > 1 ? tail[tail.length - 2]?.total_bad_exit_cost_usd_est : null;
  const lastCost = tail.length ? tail[tail.length - 1]?.total_bad_exit_cost_usd_est : null;
  const trend =
    typeof prevCost === "number" && typeof lastCost === "number"
      ? lastCost < prevCost
        ? "↓ iyileşiyor"
        : lastCost > prevCost
          ? "↑ kötüleşiyor"
          : "→ sabit"
      : null;

  return (
    <PanelFrame id="exit_forensics">
      <PanelHeader
        title="Çıkış Otopsisi"
        subtitle="Para nerede masada kaldı, stop nerede geri verdi"
        actions={
          d && trend ? (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                trend.startsWith("↓")
                  ? "bg-signal-up/20 text-signal-up"
                  : trend.startsWith("↑")
                    ? "bg-signal-down/20 text-signal-down"
                    : "bg-white/10 text-white/60"
              }`}
            >
              {trend}
            </span>
          ) : null
        }
      />

      {d && d.usable > 0 ? (
        <>
          {d.top_costs.length ? (
            <div className="mb-2 space-y-1.5">
              <div className="text-[10px] font-bold uppercase tracking-wide text-white/40">
                En pahalı 3 çıkış hatası
              </div>
              {d.top_costs.map((c, i) => (
                <div
                  key={`${c.kind}-${c.timeframe}`}
                  className="rounded border border-white/10 bg-black/20 px-2 py-1.5"
                >
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[11px] font-bold text-white/70">#{i + 1}</span>
                    <span
                      className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                        KIND_CHIP[c.kind] ?? "bg-white/10 text-white/60"
                      }`}
                    >
                      {c.timeframe} · n={c.n}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-white/75">{c.label}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
              Konuşacak kadar veri biriken kovada (≥{d.min_bucket} işlem) belirgin çıkış hatası yok.
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">TF</th>
                  <th className="py-0.5 pr-2 font-medium">Çıkış</th>
                  <th className="py-0.5 pr-2 text-right font-medium">N</th>
                  <th className="py-0.5 pr-2 text-right font-medium">PnL</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Yakalama</th>
                  <th className="py-0.5 text-right font-medium">
                    Kaçan <span className="text-white/30">(tahmini)</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((b) => {
                  const cost = bucketCost(b);
                  return (
                    <tr key={`${b.timeframe}-${b.category}`} className="border-t border-white/5">
                      <td className="py-0.5 pr-2 font-mono text-white/70">{b.timeframe}</td>
                      <td className="py-0.5 pr-2 text-white/60">
                        {CATEGORY_LABEL[b.category] ?? b.category}
                        {b.category === "sl" && b.sl_roundtrip > 0 ? (
                          <span className="ml-1 text-signal-down/80">({b.sl_roundtrip} geri-dönüş)</span>
                        ) : null}
                      </td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{b.n}</td>
                      <td
                        className={`py-0.5 pr-2 text-right font-mono ${
                          b.total_pnl >= 0 ? "text-signal-up/80" : "text-signal-down/80"
                        }`}
                      >
                        ${b.total_pnl.toFixed(0)}
                      </td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">
                        {b.avg_capture === null ? "—" : `%${Math.round(b.avg_capture * 100)}`}
                      </td>
                      <td className="py-0.5 text-right font-mono text-amber-300/80">{usd(cost)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            <div>
              Dışarıda: {d.excluded.manual ?? 0} manuel · {d.excluded.non_auto ?? 0} test/bilinmeyen ·{" "}
              {d.excluded.no_excursion ?? 0} eski kayıt (MFE/MAE yok) — bunlar robotun karnesine girmez.
            </div>
            {d.limits.map((l) => (
              <div key={l}>⚠ {l}</div>
            ))}
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz otopsi yapılacak AUTO işlem yok. Robot işlem kapattıkça bu panel dolacak.
        </div>
      )}
    </PanelFrame>
  );
}
