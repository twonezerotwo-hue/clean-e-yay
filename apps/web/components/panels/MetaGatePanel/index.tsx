"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useMetaGate } from "@/lib/queries/hooks";
import type { MetaGateView } from "@/types/uncontracted";

// Y-5 — Meta-label kapısı (SALT-GÖLGE). Yön sinyalini TAHMİN ETMEZ; robotun
// açmak üzere olduğu her işleme mevcut kanıttan "GİR / GİRME" diye ikinci bir
// görüş verir. Bu görüş karara/boyuta ASLA uygulanmaz — sadece deftere yazılır.
// Amaç: kapı gerçekten seçici mi (dediği "GİR"ler dediği "GİRME"lerden iyi mi)
// ölçülsün; aktivasyon ayrı bir owner kararıdır (kırmızı çizgi). Panel HESAP
// YAPMAZ; tüm sayılar /learning/meta-gate'ten gelir.

function usd(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `$${v.toFixed(0)}`;
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `%${Math.round(v * 100)}`;
}

export function MetaGatePanel() {
  const { data, isLoading } = useMetaGate();

  if (isLoading) {
    return (
      <PanelFrame id="meta_gate">
        <PanelHeader title="Meta-Kapı (GİR/GİRME)" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: MetaGateView | undefined = data;
  const buckets = Object.entries(d?.buckets ?? {}).sort(
    (a, b) => b[1].quality_score - a[1].quality_score,
  );
  const sc = d?.scorecard;
  const take = sc?.by_verdict.TAKE;
  const skip = sc?.by_verdict.SKIP;

  return (
    <PanelFrame id="meta_gate">
      <PanelHeader
        title="Meta-Kapı (GİR/GİRME)"
        subtitle="İkinci görüş — işlem seçiciliğini ölçer, karara dokunmaz"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            salt-gölge
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          {/* Seçicilik karnesi — aktivasyonun tek meşru dayanağı. */}
          <div className="mb-2 grid grid-cols-2 gap-1.5">
            {[
              { label: "GİR dedikleri", stat: take, tone: "up" as const },
              { label: "GİRME dedikleri", stat: skip, tone: "down" as const },
            ].map(({ label, stat, tone }) => (
              <div
                key={label}
                className="rounded border border-white/10 bg-black/20 px-2 py-1.5"
              >
                <div className="text-[10px] font-bold uppercase tracking-wide text-white/40">
                  {label}
                </div>
                <div className="mt-0.5 flex items-baseline gap-1.5">
                  <span
                    className={`font-mono text-sm font-bold ${
                      tone === "up" ? "text-signal-up/90" : "text-signal-down/90"
                    }`}
                  >
                    {pct(stat?.win_rate)}
                  </span>
                  <span className="text-[10px] text-white/40">isabet</span>
                </div>
                <div className="text-[10px] text-white/50">
                  n={stat?.n ?? 0} · PnL {usd(stat?.pnl)}
                </div>
              </div>
            ))}
          </div>

          <div
            className={`mb-2 rounded border px-2 py-1.5 text-[11px] leading-4 ${
              sc?.selective
                ? "border-signal-up/30 bg-signal-up/10 text-signal-up/90"
                : "border-white/10 bg-white/[0.02] text-white/55"
            }`}
          >
            {sc?.selective
              ? "✓ Kapı şu ana dek seçici: “GİR” dedikleri “GİRME”lerden hem daha isabetli hem daha kârlı. Aktivasyon yine de ayrı owner kararı."
              : "Kapı henüz seçicilik kanıtı vermedi — “GİR”ler “GİRME”leri net geçmeden aktivasyon gündeme gelmez."}
            {sc?.unmatched ? (
              <span className="text-white/35">
                {" "}
                ({sc.unmatched} kapanış kapının görüşünü almadan gerçekleşti)
              </span>
            ) : null}
          </div>

          {/* Bariyer-kalite kovaları — kapının "iyi işlem" öğrendiği yüzey. */}
          {buckets.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-left text-white/40">
                    <th className="py-0.5 pr-2 font-medium">Sinyal · TF</th>
                    <th className="py-0.5 pr-2 text-right font-medium">N</th>
                    <th className="py-0.5 pr-2 text-right font-medium">Hakiki</th>
                    <th className="py-0.5 pr-2 text-right font-medium">Kötü</th>
                    <th className="py-0.5 text-right font-medium">Kalite</th>
                  </tr>
                </thead>
                <tbody>
                  {buckets.map(([key, b]) => (
                    <tr key={key} className="border-t border-white/5">
                      <td className="py-0.5 pr-2 font-mono text-white/70">
                        {key.replace("|", " · ")}
                      </td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">{b.n}</td>
                      <td className="py-0.5 pr-2 text-right font-mono text-signal-up/70">
                        {b.good}
                      </td>
                      <td className="py-0.5 pr-2 text-right font-mono text-signal-down/70">
                        {b.bad}
                      </td>
                      <td
                        className={`py-0.5 text-right font-mono ${
                          b.quality_score > 0
                            ? "text-signal-up/80"
                            : b.quality_score < 0
                              ? "text-signal-down/80"
                              : "text-white/50"
                        }`}
                      >
                        {b.quality_score >= 0 ? "+" : ""}
                        {b.quality_score.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
              Kovalarda henüz konuşacak kadar (≥{d.config.min_bucket_n} işlem) tarihçe yok.
            </div>
          )}
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Kapı tablosu henüz üretilmedi. Robot AUTO işlem kapattıkça ve öğrenme
          döngüsü çalıştıkça bu panel dolacak.
        </div>
      )}
    </PanelFrame>
  );
}
