"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useMissedOpportunities } from "@/lib/queries/hooks";
import type { MissedOpportunitiesView } from "@/types/generated/api";

// Faz 2 — Missed Opportunity (packages/learning/missed_opportunity.py).
// Açılmayan valid setup'ları (CANDIDATE_OPEN ama canlı açmadı) TTL boyunca izler:
// fiyat önce TP'ye mi (missed_win) SL'e mi (avoided_loss) değdi? Frontend hesap
// YAPMAZ; tüm sayım /api/v1/learning/missed-opportunities ViewModel'inden gelir.
// PAPER_SAFE — paper'a dokunmaz; Faz 4 (conflict-gate genişletme) kararına veri.

const OUTCOME_LABEL: Record<string, string> = {
  missed_win: "Kaçan kazanç",
  avoided_loss: "Önlenen zarar",
  expired: "Süre doldu",
};

export function MissedOpportunitiesPanel() {
  const { data, isLoading } = useMissedOpportunities();

  if (isLoading) {
    return (
      <PanelFrame id="missed_opportunities">
        <PanelHeader title="Kaçan Fırsatlar" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const d: MissedOpportunitiesView | undefined = data;
  const enabled = !!d?.enabled;
  const oc = d?.outcomes ?? { missed_win: 0, avoided_loss: 0, expired: 0 };
  const profiles = d?.by_profile ? Object.keys(d.by_profile) : [];
  const active = d?.active ?? [];

  return (
    <PanelFrame id="missed_opportunities">
      <PanelHeader
        title="Kaçan Fırsatlar"
        subtitle="Açılmayan valid setup'ların TTL sonucu"
        actions={
          <span
            className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
              enabled
                ? "bg-signal-up/20 text-signal-up"
                : "bg-white/10 text-white/55"
            }`}
          >
            {enabled ? "TOPLUYOR" : "KAPALI"}
          </span>
        }
      />
      <p className="mb-2 rounded border border-white/10 bg-white/[0.02] px-2 py-1 text-[11px] text-white/55">
        {enabled
          ? "Açılmayan CANDIDATE_OPEN setuplar izleniyor; sonuçlar Faz 4 gate kararına veri."
          : "Gözlem KAPALI. missed_opportunity.enabled=true ile toplamaya başla (paper'a dokunmaz)."}
      </p>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded border border-signal-up/25 bg-signal-up/5 px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-signal-up">{oc.missed_win}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">{OUTCOME_LABEL.missed_win}</div>
        </div>
        <div className="rounded border border-signal-down/25 bg-signal-down/5 px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-signal-down">{oc.avoided_loss}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">{OUTCOME_LABEL.avoided_loss}</div>
        </div>
        <div className="rounded border border-white/10 bg-white/[0.02] px-2 py-2">
          <div className="text-lg font-semibold tabular-nums text-white/70">{oc.expired}</div>
          <div className="text-[10px] uppercase tracking-wide text-white/45">{OUTCOME_LABEL.expired}</div>
        </div>
      </div>

      {profiles.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[18rem] border-collapse text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-white/40">
                <th className="p-1 text-left font-normal">Profil</th>
                <th className="p-1 font-normal text-signal-up">Kaçan</th>
                <th className="p-1 font-normal text-signal-down">Önlenen</th>
                <th className="p-1 font-normal text-white/50">Süre</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => {
                const row = d!.by_profile[p];
                return (
                  <tr key={p} className="border-t border-white/5">
                    <td className="p-1 font-medium uppercase tracking-wide text-[11px]">{p}</td>
                    <td className="p-1 text-center tabular-nums text-signal-up">{row.missed_win}</td>
                    <td className="p-1 text-center tabular-nums text-signal-down">{row.avoided_loss}</td>
                    <td className="p-1 text-center tabular-nums text-white/60">{row.expired}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-3 text-[10px] uppercase tracking-widest text-white/35">
        Aktif izleme ({active.length})
      </div>
      {active.length ? (
        <ul className="mt-1 space-y-0.5 text-[11px] tabular-nums text-white/65">
          {active.slice(0, 8).map((a, i) => (
            <li key={`${a.symbol}-${a.timeframe}-${a.side}-${i}`} className="flex justify-between">
              <span>
                <span className="font-medium">{a.symbol}</span>{" "}
                <span className="text-white/40">{a.timeframe}</span>{" "}
                <span className={a.side === "long" ? "text-signal-up" : "text-signal-down"}>
                  {a.side}
                </span>
                {a.trade_profile ? <span className="text-white/35"> · {a.trade_profile}</span> : null}
              </span>
              <span className="text-white/40">
                {a.entry != null ? a.entry : "—"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-1 text-[11px] text-white/35">Şu an izlenen aday yok.</div>
      )}
    </PanelFrame>
  );
}
