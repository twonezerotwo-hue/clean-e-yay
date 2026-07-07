"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useNewsEventStudy } from "@/lib/queries/hooks";
import type { NewsEventStudyView } from "@/types/uncontracted";

// Y-6 — Haber olay-çalışması (SALT-GÖZLEM). Sorusu basit: "bir haber çıktıktan
// sonra fiyat gerçekten haberin dediği yöne mi gidiyor, yoksa gürültü mü?" Her
// haber damgalanır, N bar sonrası getirisi ölçülür, kaynak × ton kovasında
// biriktirilir. Kanıt yeterli değilse dürüstçe "kanıtsız" der. Hiçbir sayı
// karara/ağırlığa dokunmaz. Panel HESAP YAPMAZ; her şey backend'ten gelir.

const SENTIMENT_LABEL: Record<string, string> = {
  bullish: "yükseliş",
  bearish: "düşüş",
  neutral: "nötr",
};

const VERDICT_CHIP: Record<string, { label: string; cls: string }> = {
  PREDICTIVE: { label: "öngörüyor", cls: "bg-signal-up/20 text-signal-up" },
  NO_EDGE: { label: "edge yok", cls: "bg-white/10 text-white/55" },
  INSUFFICIENT: { label: "kanıtsız", cls: "bg-amber-400/15 text-amber-300/80" },
};

export function NewsEventStudyPanel() {
  const { data, isLoading } = useNewsEventStudy();

  if (isLoading) {
    return (
      <PanelFrame id="news_event_study">
        <PanelHeader title="Haberin Edge'i" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: NewsEventStudyView | undefined = data;
  const buckets = Object.entries(d?.buckets ?? {}).sort(
    (a, b) => b[1].n - a[1].n,
  );
  const proven = d?.global_verdict === "PREDICTIVE";

  return (
    <PanelFrame id="news_event_study">
      <PanelHeader
        title="Haberin Edge'i"
        subtitle="Haber sonrası fiyat gerçekten yönü tutuyor mu — ölçer, karar vermez"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            salt-gözlem
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          <div
            className={`mb-2 rounded border px-2 py-1.5 text-[11px] leading-4 ${
              proven
                ? "border-signal-up/30 bg-signal-up/10 text-signal-up/90"
                : "border-white/10 bg-white/[0.02] text-white/55"
            }`}
          >
            {proven
              ? "✓ En az bir haber kovası öngörü gösteriyor — sonrası fiyat haberin yönünü tutuyor. Yine de ağırlığa dokunmaz; challenger'a görünürlük ayrı owner kararı."
              : "Haber ağırlığı henüz kanıtsız — hiçbir kova “haber → yön” öngörüsü göstermedi. Kanıt her haftayla birikiyor (dürüst sonuç, uydurma yok)."}
          </div>

          <div className="mb-2 text-[10px] text-white/40">
            {d.matured} olgunlaşmış · {d.pending} bekleyen ({d.horizon_bars} bar sonrası
            ölçülür) · toplam {d.events_total} haber damgası
          </div>

          {buckets.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-left text-white/40">
                    <th className="py-0.5 pr-2 font-medium">Kaynak · Ton</th>
                    <th className="py-0.5 pr-2 text-right font-medium">N</th>
                    <th className="py-0.5 pr-2 text-right font-medium">İsabet</th>
                    <th className="py-0.5 pr-2 text-right font-medium">Ort. getiri</th>
                    <th className="py-0.5 text-right font-medium">Hüküm</th>
                  </tr>
                </thead>
                <tbody>
                  {buckets.map(([key, b]) => {
                    const [source, sentiment] = key.split("|");
                    const chip = VERDICT_CHIP[b.verdict] ?? VERDICT_CHIP.INSUFFICIENT;
                    return (
                      <tr key={key} className="border-t border-white/5">
                        <td className="py-0.5 pr-2 text-white/70">
                          <span className="font-mono">{source}</span>
                          <span className="text-white/40">
                            {" "}
                            · {SENTIMENT_LABEL[sentiment] ?? sentiment}
                          </span>
                        </td>
                        <td className="py-0.5 pr-2 text-right font-mono text-white/60">{b.n}</td>
                        <td className="py-0.5 pr-2 text-right font-mono text-white/60">
                          {b.hit_rate === null ? "—" : `%${Math.round(b.hit_rate * 100)}`}
                        </td>
                        <td
                          className={`py-0.5 pr-2 text-right font-mono ${
                            b.avg_dir_return_pct > 0
                              ? "text-signal-up/80"
                              : b.avg_dir_return_pct < 0
                                ? "text-signal-down/80"
                                : "text-white/50"
                          }`}
                        >
                          {b.avg_dir_return_pct >= 0 ? "+" : ""}
                          {b.avg_dir_return_pct.toFixed(2)}%
                        </td>
                        <td className="py-0.5 text-right">
                          <span
                            className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${chip.cls}`}
                          >
                            {chip.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
              Henüz olgunlaşmış haber olayı yok. Haberler damgalandıkça ve {d.horizon_bars}{" "}
              bar geçtikçe bu tablo dolacak.
            </div>
          )}
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Haber karnesi henüz üretilmedi. Öğrenme döngüsü çalıştıkça haberler
          damgalanacak ve sonrasındaki fiyat hareketi ölçülecek.
        </div>
      )}
    </PanelFrame>
  );
}
