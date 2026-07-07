"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { usePayoffReadiness } from "@/lib/queries/hooks";
import type { PayoffReadinessView } from "@/types/uncontracted";

// Faz-A (EV kapısı) — EV kapısı, bir işlemin beklenen değeri artı mı diye bakar.
// "Payoff EV" daha dürüst bir hesap: kazançların/kayıpların GERÇEKLEŞEN R'sini
// kullanır (trailing/time-stop hedeften erken kesince asimetriyi görür). Ama bir
// hücrede bunu güvenle kullanmak için her iki yönde de yeterli örnek şart. Bu
// panel her hücrenin eşiğe (min_r_samples) ne kadar yakın olduğunu gösterir —
// owner en dolu hücrenin eşiği geçişini izler. Panel HESAP YAPMAZ.

export function PayoffReadinessPanel() {
  const { data, isLoading } = usePayoffReadiness();

  if (isLoading) {
    return (
      <PanelFrame id="payoff_readiness">
        <PanelHeader title="Payoff EV Hazırlığı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: PayoffReadinessView | undefined = data;
  // en yakın önce: hazır olanlar üstte, sonra eşiğe kalanı az olan.
  const rows = [...(d?.per_cell ?? [])].sort(
    (a, b) => a.short_by - b.short_by || b.win_r_n - a.win_r_n,
  );

  return (
    <PanelFrame id="payoff_readiness">
      <PanelHeader
        title="Payoff EV Hazırlığı"
        subtitle="Hangi hücre gerçekleşen-R kâr hesabına geçecek kadar örnek gördü"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            eşik {d?.min_r_samples ?? 8}
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          <div className="mb-2 text-[11px] leading-4 text-white/55">
            {d.ready_count > 0
              ? `${d.ready_count} hücre payoff EV'sine hazır (${d.ready_cells.join(", ")}).`
              : d.closest_cell
                ? `Henüz hiçbir hücre hazır değil. En yakın: ${d.closest_cell.cell} — eşiğe ${d.closest_cell.short_by} örnek kaldı.`
                : "Henüz gerçekleşen-R verisi yok."}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">Hücre (TF·rejim)</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Kazanç-R</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Kayıp-R</th>
                  <th className="py-0.5 text-right font-medium">Durum</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.cell} className="border-t border-white/5">
                    <td className="py-0.5 pr-2 font-mono text-white/70">
                      {r.cell.replace("|", " · ")}
                    </td>
                    <td
                      className={`py-0.5 pr-2 text-right font-mono ${
                        r.win_r_n >= r.min_r_samples ? "text-signal-up/80" : "text-white/60"
                      }`}
                    >
                      {r.win_r_n}/{r.min_r_samples}
                    </td>
                    <td
                      className={`py-0.5 pr-2 text-right font-mono ${
                        r.loss_r_n >= r.min_r_samples ? "text-signal-up/80" : "text-white/60"
                      }`}
                    >
                      {r.loss_r_n}/{r.min_r_samples}
                    </td>
                    <td className="py-0.5 text-right">
                      {r.payoff_ready ? (
                        <span className="rounded bg-signal-up/20 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide text-signal-up">
                          hazır
                        </span>
                      ) : (
                        <span className="text-white/45">−{r.short_by}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[10px] leading-4 text-white/45">
            Hazır hücrelerde EV gerçekleşen kâr/zarar-R'sini kullanır; kalanlar
            dürüstçe sabit hedef-RR'ye düşer (uydurma payoff yok — guard canlı).
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz gerçekleşen-R verisi yok. İşlemler R-damgalı kapandıkça hücreler
          eşiğe doğru dolacak.
        </div>
      )}
    </PanelFrame>
  );
}
