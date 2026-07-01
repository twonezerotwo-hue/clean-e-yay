"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useEdgeReport } from "@/lib/queries/hooks";
import type { EdgeReportView } from "@/types/generated/api";

// CP2 — edge kanıt/stabilite paneli. Biriken outcome'lar üstünde çok-katlı
// walk-forward stabilite (edge tutarlı mı, fluke mı) + missed opportunity
// counterfactual. Frontend hesap YAPMAZ; tüm sayım /learning/edge-report'tan.
// Gerçek historical backtest ayrı (Soul/replay); bu hafif güven katmanı.

const VERDICT: Record<string, { label: string; chip: string }> = {
  STABLE: { label: "STABİL", chip: "bg-signal-up/20 text-signal-up" },
  UNSTABLE: { label: "TUTARSIZ", chip: "bg-signal-down/20 text-signal-down" },
  INSUFFICIENT: { label: "YETERSİZ", chip: "bg-white/10 text-white/55" },
};

export function EdgeReportPanel() {
  const { data, isLoading } = useEdgeReport();

  if (isLoading) {
    return (
      <PanelFrame id="edge_report">
        <PanelHeader title="Kazanç Tutarlılığı" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: EdgeReportView | undefined = data;
  const v = VERDICT[d?.verdict ?? "INSUFFICIENT"] ?? VERDICT.INSUFFICIENT;
  const stab = d?.stability;
  const cf = d?.counterfactual;

  return (
    <PanelFrame id="edge_report">
      <PanelHeader
        title="Kazanç Tutarlılığı"
        subtitle="Sistemin avantajı kalıcı mı, şans mı"
        actions={
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${v.chip}`}>
            {v.label}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] leading-5 text-white/55">
        Kapanan işlemleri zaman dilimlerine bölüp kazanç oranının <strong className="text-white/75">tutarlı</strong>
        {" "}olup olmadığına bakar. Stabil değilse otomatik ince-ayar güvenli değildir.
      </p>

      {stab?.ready ? (
        <>
          <div className="flex flex-wrap gap-1.5">
            {stab.segments.map((s, i) => (
              <div
                key={i}
                className="rounded border border-white/10 bg-black/20 px-2 py-1 text-center"
                title={`Segment ${i + 1}: ${s.n} işlem, beklenti ${s.expectancy}`}
              >
                <div
                  className={`font-mono text-xs font-semibold tabular-nums ${
                    s.expectancy > 0 ? "text-signal-up" : "text-signal-down"
                  }`}
                >
                  %{Math.round(s.win_rate * 100)}
                </div>
                <div className="text-[9px] uppercase tracking-wide text-white/35">S{i + 1}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-white/55">
            <span>
              Oynaklık (std): <span className="tabular-nums text-white/80">{stab.win_rate_std}</span>
            </span>
            <span>
              Pozitif dilim:{" "}
              <span className="tabular-nums text-white/80">
                {stab.positive_folds}/{stab.folds}
              </span>
            </span>
          </div>
        </>
      ) : (
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2 text-[11px] text-white/50">
          Yeterli kapanmış işlem yok ({stab?.have ?? 0}/{stab?.need ?? "—"}). Veri biriktikçe stabilite ölçülür.
        </div>
      )}

      {cf && (cf.missed_win || cf.avoided_loss || cf.expired) ? (
        <div className="mt-2 flex gap-2 text-[10px] uppercase tracking-wide text-white/45">
          <span>Kaçan: <span className="text-signal-up">{cf.missed_win}</span></span>
          <span>Önlenen: <span className="text-signal-down">{cf.avoided_loss}</span></span>
          <span>Süre: <span className="text-white/60">{cf.expired}</span></span>
        </div>
      ) : null}

      {d?.outlier_concentration != null ? (
        <div
          className={`mt-2 rounded border px-2 py-1 text-[10px] ${
            d.outlier_dependent
              ? "border-amber-400/30 bg-amber-400/5 text-amber-300/90"
              : "border-white/10 bg-white/[0.02] text-white/45"
          }`}
        >
          Tek-işlem yoğunlaşması: <span className="tabular-nums">%{Math.round((d.outlier_concentration ?? 0) * 100)}</span>
          {" "}(eşik %{Math.round((d.max_outlier_concentration ?? 0.35) * 100)})
          {d.outlier_dependent ? " — edge tek işleme bağımlı, autotune kilitli" : ""}
          {" · "}rejim etiketi %{Math.round((d.regime_coverage ?? 0) * 100)}
        </div>
      ) : null}
    </PanelFrame>
  );
}
