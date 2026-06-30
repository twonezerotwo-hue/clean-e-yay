"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useMistakes } from "@/lib/queries/hooks";
import {
  selectCounts,
  selectFlagged,
  selectRecordsByFp,
} from "@/lib/selectors/mistakes";
import { fmtNum, fmtPct, fmtRelative } from "@/lib/format";
import type { MistakeAction } from "@/types/generated/api";

const ACTION_TONE: Record<MistakeAction, string> = {
  AVOID: "bg-signal-down/20 text-signal-down",
  BOOST: "bg-signal-up/20 text-signal-up",
  WARNING: "bg-amber-400/20 text-amber-400",
  NEUTRAL: "bg-white/10 text-white/50",
};

/**
 * G3 — Mistake memory paneli. Geçmiş benzer hatalar + verdict + size
 * adjustment. RiskGate ve DQS hard gate'leri her zaman önce çalışır;
 * mistake memory yalnızca avoid/boost/warning üretir.
 */
export function MistakeMemoryPanel() {
  const { data, isLoading } = useMistakes();
  if (isLoading) {
    return (
      <PanelFrame id="mistake_memory">
        <PanelHeader title="Hata Hafızası" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const { total, flagged } = selectCounts(data);
  const flaggedItems = selectFlagged(data);
  const byFp = selectRecordsByFp(data);

  if (!total) {
    return (
      <PanelFrame id="mistake_memory">
        <PanelHeader title="Hata Hafızası" subtitle="benzer geçmiş hata yok" />
        <EmptyState />
        <p className="mt-2 text-[11px] text-white/40">
          Yeterli doğrulanmış trade yok — neutral fallback (no_adjustment).
        </p>
      </PanelFrame>
    );
  }
  return (
    <PanelFrame id="mistake_memory">
      <PanelHeader
        title="Hata Hafızası"
        subtitle={`${total} durum · ${flagged} riskli işaretli`}
        actions={
          <span className="text-[10px] uppercase tracking-widest text-white/40">
            RiskGate / DQS ile birlikte çalışır
          </span>
        }
      />
      {flaggedItems.length === 0 ? (
        <p className="text-xs text-white/40">
          Tüm fingerprint'ler NEUTRAL — adjustment uygulanmıyor.
        </p>
      ) : (
        <ul className="space-y-2 text-xs">
          {flaggedItems.map((v) => {
            const rec = byFp.get(v.fingerprint);
            return (
              <li
                key={v.fingerprint}
                className="border-b border-white/5 pb-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-white/70 truncate">
                    {v.fingerprint}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${ACTION_TONE[v.action]}`}
                  >
                    {v.action}
                  </span>
                </div>
                <div className="mt-0.5 text-white/50 flex items-center gap-3">
                  <span>{v.reason}</span>
                  <span className="tabular-nums">size× {fmtNum(v.size_factor, 2)}</span>
                </div>
                {rec ? (
                  <div className="mt-0.5 flex items-center gap-3 text-[11px] text-white/40 tabular-nums">
                    <span>trades {rec.trades}</span>
                    <span>win {fmtPct(rec.win_rate, 0)}</span>
                    <span>pnl {fmtNum(rec.total_pnl, 0)}</span>
                    <span>streak {rec.streak_losses}</span>
                    <span>{fmtRelative(rec.last_seen_at)}</span>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </PanelFrame>
  );
}
