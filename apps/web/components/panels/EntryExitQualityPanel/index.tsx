"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useEntryExitQuality } from "@/lib/queries/hooks";
import type { EntryExitQualityView } from "@/types/generated/api";

// CP4 (slice 1) — giriş/çıkış kalitesi paneli. Biriken verified outcome'ların
// MAE/MFE excursion'ından, dominant_module × timeframe bazında üç dersi gösterir:
// erken çıkış (kâr masada), dar stop (gürültüde tetikleniyor), erken giriş.
// TF-target trainer'ın yalnız-TF granülerliğindeki boşluğu kapatır. Frontend
// hesap YAPMAZ; tüm sayım /learning/entry-exit-quality'den. Observe-only.

const VERDICT: Record<string, { label: string; chip: string }> = {
  EXIT_EARLY: { label: "Erken Çıkış", chip: "bg-amber-400/20 text-amber-300" },
  STOP_TOO_TIGHT: { label: "Dar Stop", chip: "bg-signal-down/20 text-signal-down" },
  ENTER_EARLY: { label: "Erken Giriş", chip: "bg-amber-400/20 text-amber-300" },
};

function pct(v: number | null): string {
  return v === null ? "—" : `%${Math.round(v * 100)}`;
}

export function EntryExitQualityPanel() {
  const { data, isLoading } = useEntryExitQuality();

  if (isLoading) {
    return (
      <PanelFrame id="entry_exit_quality">
        <PanelHeader title="Giriş/Çıkış Kalitesi" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: EntryExitQualityView | undefined = data;
  const flagged = (d?.buckets ?? []).filter((b) => b.verdicts.length > 0);

  return (
    <PanelFrame id="entry_exit_quality">
      <PanelHeader
        title="Giriş/Çıkış Kalitesi"
        subtitle="Geç mi girdim, erken mi çıktım, stop dar mı"
        actions={
          d ? (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                flagged.length
                  ? "bg-amber-400/20 text-amber-300"
                  : "bg-signal-up/20 text-signal-up"
              }`}
            >
              {flagged.length ? `${flagged.length} sorunlu kova` : "temiz"}
            </span>
          ) : null
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Kapanan işlemlerin MAE/MFE hareketinden, <strong className="text-white/75">modül × zaman dilimi</strong>{" "}
        bazında çıkışın erken (kâr masada), stop'un dar veya girişin erken olup olmadığını öğrenir.
        Önerilerin otonom uygulanması ayrı bir aşama (rollback ağıyla).
      </p>

      {d && d.usable > 0 ? (
        flagged.length ? (
          <div className="space-y-2">
            {flagged.map((b, i) => {
              const m = b.metrics;
              return (
                <div key={i} className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-semibold text-white/85">
                      {b.module} · {b.timeframe}
                    </span>
                    <div className="flex gap-1">
                      {b.verdicts.map((v) => {
                        const vd = VERDICT[v.code] ?? { label: v.code, chip: "bg-white/10 text-white/60" };
                        return (
                          <span
                            key={v.code}
                            className={`rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${vd.chip}`}
                          >
                            {vd.label}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-white/45">
                    <span>n={m.n_usable}</span>
                    <span>yakalama {pct(m.avg_capture_ratio)}</span>
                    <span>
                      bırakılan kâr{" "}
                      <span className="text-amber-300/80">
                        {m.avg_give_back_pct === null ? "—" : `%${m.avg_give_back_pct.toFixed(2)}`}
                      </span>
                    </span>
                    {m.n_sl_hit > 0 ? <span>stop {pct(m.sl_hit_rate)}</span> : null}
                  </div>
                  {b.verdicts.map((v) => (
                    <p key={v.code} className="mt-1 text-[10px] leading-4 text-white/60">
                      → {v.detail}
                    </p>
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
            {d.usable} kullanılabilir işlemde belirgin giriş/çıkış hatası yok — yakalama oranları sağlıklı.
          </div>
        )
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Yeterli MAE/MFE'li işlem yok. Veri biriktikçe kovalar (≥{d?.min_bucket ?? 4} işlem) ders üretir.
        </div>
      )}
    </PanelFrame>
  );
}
