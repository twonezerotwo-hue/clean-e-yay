"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useTfWeights } from "@/lib/queries/hooks";
import type { TfCalibrationRow, TfWeightsReport } from "@/types/generated/api";

// Step 8 — per-TF calibration + the trust-gated tf_weights proposal. Backend computes
// hit-rate/expectancy per timeframe from VERIFIED outcomes and proposes weight nudges
// only for validated (CALIBRATED) timeframes. Owner approves — live weights are never
// auto-moved. Frontend does no math; all values come from the ViewModel.

const STATUS_LABEL: Record<string, string> = {
  proposed: "öneri hazır",
  no_calibrated_tf: "henüz doğrulanmış TF yok",
  no_change: "değişiklik önerilmiyor",
  no_prior_weights: "PRIOR ağırlık yok",
};

function trustTone(trust: string): string {
  return trust === "CALIBRATED"
    ? "border-signal-up/40 text-signal-up bg-signal-up/5"
    : "border-white/10 text-white/45";
}

function CalRow({ row }: { row: TfCalibrationRow }) {
  return (
    <tr className="border-t border-white/5">
      <td className="p-1 font-medium">{row.timeframe}</td>
      <td className="p-1 text-white/55">{row.strategy}</td>
      <td className="p-1 text-center tabular-nums">{row.trades}</td>
      <td className="p-1 text-center tabular-nums">{Math.round((row.win_rate ?? 0) * 100)}%</td>
      <td className="p-1 text-center">
        <span className={`rounded border px-1.5 py-0.5 text-[10px] ${trustTone(row.trust)}`}>
          {row.trust}
        </span>
      </td>
    </tr>
  );
}

export function TfWeightsPanel() {
  const { data, isLoading } = useTfWeights();
  if (isLoading) {
    return (
      <PanelFrame id="tf_weights">
        <PanelHeader title="Zaman Dilimi Ağırlıkları" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const d: TfWeightsReport | undefined = data;
  const rows = d?.per_timeframe ?? [];
  const trusted = !!d?.tf_weights_trusted;
  const status = d?.proposal_status ?? "";
  return (
    <PanelFrame id="tf_weights">
      <PanelHeader
        title="Zaman Dilimi Ağırlıkları"
        subtitle="Hangi zaman dilimine ne kadar güveniliyor (önerir, sen onaylarsın)"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
              trusted ? "bg-signal-up/20 text-signal-up" : "bg-white/10 text-white/55"
            }`}
          >
            {trusted ? "CALIBRATED" : "PRIOR"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        {trusted
          ? "Zaman dilimi güvenleri doğrulandı — öneri verilebilir."
          : "Zaman dilimi güvenleri henüz doğrulanmadı · yeterli kanıt birikene kadar güvenilmiyor."}{" "}
        Durum: <b>{STATUS_LABEL[status] ?? status}</b>. Değişikliği sen onaylarsın; canlı
        ağırlık asla otomatik taşınmaz.
      </p>
      {!rows.length ? (
        <EmptyState message="Henüz verified outcome yok — kalibrasyon birikiyor." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[20rem] border-collapse text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-white/40">
                <th className="p-1 text-left font-normal">TF</th>
                <th className="p-1 text-left font-normal">Strateji</th>
                <th className="p-1 font-normal">Trade</th>
                <th className="p-1 font-normal">Win</th>
                <th className="p-1 font-normal">Trust</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <CalRow key={`${r.strategy}:${r.timeframe}`} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d?.deltas?.length ? (
        <div className="mt-2 rounded border border-amber-400/30 bg-amber-400/5 px-2 py-1.5">
          <div className="mb-1 text-[10px] uppercase tracking-widest text-amber-300/80">
            Önerilen ağırlık değişimi (onay bekler)
          </div>
          <ul className="space-y-0.5 text-[11px] tabular-nums text-white/70">
            {d.deltas.map((dl) => (
              <li key={`${dl.strategy}:${dl.timeframe}`}>
                {dl.strategy}.{dl.timeframe}: {dl.old.toFixed(2)} →{" "}
                <span className={dl.delta >= 0 ? "text-signal-up" : "text-signal-down"}>
                  {dl.new.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="mt-2 text-[10px] text-white/35">
        Adım 8 · entry-outcome tabanlı, trust-gated. Tam per-TF contribution attribution
        ertelendi (faking yok). Onaylanan ağırlıklar ayrı akışla canlıya uygulanır.
      </p>
    </PanelFrame>
  );
}
