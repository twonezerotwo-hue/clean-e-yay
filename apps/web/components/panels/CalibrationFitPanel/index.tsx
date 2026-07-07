"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCalibrationFit } from "@/lib/queries/hooks";
import type { CalibrationFitView } from "@/types/uncontracted";

// Faz-A (Kalibrasyon) — her zaman diliminin güven ayarı (kalibrasyon) yeterince
// örnekle "oturmuş" mu? "fitted" = o TF kendi düzeltmesini kullanacak kadar veri
// gördü; "insufficient/identity" = henüz az, güvenli küresel ayara düşüyor (guard
// canlı — uydurma düzeltme uygulanmaz). Panel HESAP YAPMAZ; /learning/calibration-fit.

const STATUS_CHIP: Record<string, { label: string; cls: string }> = {
  fitted: { label: "oturmuş", cls: "bg-signal-up/20 text-signal-up" },
  insufficient: { label: "örnek az", cls: "bg-amber-400/15 text-amber-300/80" },
  identity: { label: "ham", cls: "bg-white/10 text-white/55" },
};

export function CalibrationFitPanel() {
  const { data, isLoading } = useCalibrationFit();

  if (isLoading) {
    return (
      <PanelFrame id="calibration_fit">
        <PanelHeader title="Kalibrasyon Oturmuşluğu" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: CalibrationFitView | undefined = data;
  const rows = d?.per_timeframe_fit ?? [];

  return (
    <PanelFrame id="calibration_fit">
      <PanelHeader
        title="Kalibrasyon Oturmuşluğu"
        subtitle="Hangi zaman diliminin güven-ayarı yeterli örnekle oturdu"
        actions={
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white/60">
            {d?.tf_platt_enabled ? "TF-fit açık" : "TF-fit kapalı"}
          </span>
        }
      />

      {d && d.status === "OK" ? (
        <>
          <div className="mb-2 text-[11px] leading-4 text-white/55">
            {d.any_fitted
              ? `${d.fitted_timeframes.length} zaman dilimi kendi kalibrasyonunu kullanacak kadar oturdu (${d.fitted_timeframes.join(", ")}). Kalanlar yeterli örneğe kadar güvenli küresel ayarda.`
              : "Henüz hiçbir zaman dilimi tek başına oturmadı — hepsi küresel ayarda, örnek biriktikçe tek tek geçecek."}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-left text-white/40">
                  <th className="py-0.5 pr-2 font-medium">TF</th>
                  <th className="py-0.5 pr-2 font-medium">Fit durumu</th>
                  <th className="py-0.5 pr-2 text-right font-medium">Fit örneği</th>
                  <th className="py-0.5 text-right font-medium">Güven (outcome)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const chip = STATUS_CHIP[r.fit_status] ?? STATUS_CHIP.identity;
                  return (
                    <tr key={r.timeframe} className="border-t border-white/5">
                      <td className="py-0.5 pr-2 font-mono text-white/70">{r.timeframe}</td>
                      <td className="py-0.5 pr-2">
                        <span
                          className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${chip.cls}`}
                        >
                          {chip.label}
                        </span>
                      </td>
                      <td className="py-0.5 pr-2 text-right font-mono text-white/60">
                        {r.fit_samples}
                      </td>
                      <td className="py-0.5 text-right">
                        <span
                          className={
                            r.outcome_trust === "CALIBRATED"
                              ? "text-signal-up/80"
                              : "text-white/45"
                          }
                        >
                          {r.outcome_trust === "CALIBRATED" ? "kanıtlı" : "ön-değer"}
                          <span className="text-white/35"> ({r.outcome_n})</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Henüz kalibrasyon fit verisi yok. Öğrenme döngüsü çalıştıkça ve örnek
          biriktikçe zaman dilimleri tek tek oturacak.
        </div>
      )}
    </PanelFrame>
  );
}
