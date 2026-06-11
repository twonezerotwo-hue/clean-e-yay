"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useHaltReset, useRiskHalts } from "@/lib/queries/hooks";
import {
  selectGauges,
  selectHaltActive,
  selectHaltLevel,
  selectTimeline,
} from "@/lib/selectors/halts";
import { fmtPct, fmtRelative, fmtUSD } from "@/lib/format";
import type { HaltEvent } from "@/types/generated/api";

const LEVEL_TONE: Record<string, string> = {
  KILL_SWITCH: "bg-signal-down/20 text-signal-down",
  RISK_REDUCE: "bg-amber-400/20 text-amber-400",
};

/** Oran bazlı yatay gauge — değerler backend'den gelir (ratio 0–1+). */
function RatioGauge({
  label,
  ratio,
  detail,
}: {
  label: string;
  ratio: number;
  detail: string;
}) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const tone =
    ratio >= 1
      ? "bg-signal-down"
      : ratio >= 0.5
        ? "bg-amber-400"
        : "bg-accent-cyan";
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-white/40">
        <span>{label}</span>
        <span className="tabular-nums normal-case tracking-normal text-white/60">
          {detail}
        </span>
      </div>
      <div className="mt-1 h-2 rounded bg-white/10 overflow-hidden">
        <div
          className={`h-full rounded ${tone}`}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
    </div>
  );
}

function DailyLossGauge({
  ratio,
  pnlUsd,
  limitUsd,
}: {
  ratio: number;
  pnlUsd: number;
  limitUsd: number;
}) {
  return (
    <RatioGauge
      label="Günlük Zarar"
      ratio={ratio}
      detail={`${fmtUSD(pnlUsd)} / -${fmtUSD(limitUsd)}`}
    />
  );
}

function MaxDDGauge({
  ratio,
  ddPct,
  limitPct,
}: {
  ratio: number;
  ddPct: number;
  limitPct: number;
}) {
  return (
    <RatioGauge
      label="Max Drawdown"
      ratio={ratio}
      detail={`${fmtPct(ddPct)} / ${fmtPct(limitPct, 0)}`}
    />
  );
}

function KillSwitchTimeline({ events }: { events: HaltEvent[] }) {
  if (!events.length) {
    return <p className="text-xs text-white/40">Halt geçmişi yok.</p>;
  }
  return (
    <ul className="space-y-1.5 text-xs">
      {events.slice(0, 6).map((e) => (
        <li key={e.id} className="border-b border-white/5 pb-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-white/70">{e.type}</span>
            <span
              className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${
                e.active
                  ? LEVEL_TONE[e.level]
                  : "bg-white/10 text-white/40"
              }`}
            >
              {e.active ? e.level : "CLEARED"}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-[11px] text-white/40">
            <span>{e.reason}</span>
            <span>{fmtRelative(e.started_at)}</span>
            {e.cleared_by ? <span>↳ {e.cleared_by}</span> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * G5 — Drawdown guard. Daily-loss / max-DD halt durumu + gauge'lar +
 * halt timeline. Halt sadece risk azaltıcıdır; otomatik reset yok —
 * yalnızca owner reset endpoint'i kapatır.
 */
export function DrawdownGuardPanel() {
  const { data, isLoading } = useRiskHalts();
  const reset = useHaltReset();
  if (isLoading) {
    return (
      <PanelFrame id="drawdown_guard">
        <PanelHeader title="Drawdown Guard" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const haltActive = selectHaltActive(data);
  const level = selectHaltLevel(data);
  const gauges = selectGauges(data);
  const timeline = selectTimeline(data);

  return (
    <PanelFrame id="drawdown_guard">
      <PanelHeader
        title="Drawdown Guard"
        subtitle={haltActive ? "HALT AKTİF — owner reset gerekli" : "limitler izleniyor"}
        actions={
          haltActive && level ? (
            <span
              className={`rounded px-1.5 py-0.5 uppercase tracking-wide text-[10px] ${LEVEL_TONE[level]}`}
            >
              {level}
            </span>
          ) : (
            <span className="text-[10px] uppercase tracking-widest text-white/40">
              otomatik reset yok
            </span>
          )
        }
      />
      <div className="space-y-3">
        <DailyLossGauge
          ratio={gauges.dailyLossRatio}
          pnlUsd={gauges.dailyPnlUsd}
          limitUsd={gauges.dailyLossLimitUsd}
        />
        <MaxDDGauge
          ratio={gauges.drawdownRatio}
          ddPct={gauges.drawdownPct}
          limitPct={gauges.maxDrawdownPct}
        />
      </div>
      <div className="mt-3">
        <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1.5">
          Halt Timeline
        </div>
        <KillSwitchTimeline events={timeline} />
      </div>
      {haltActive ? (
        <button
          type="button"
          disabled={reset.isPending}
          onClick={() => reset.mutate()}
          className="mt-3 rounded border border-signal-down/40 px-2 py-1 text-[11px] uppercase tracking-widest text-signal-down hover:bg-signal-down/10 disabled:opacity-50"
        >
          {reset.isPending ? "sıfırlanıyor…" : "Owner Reset"}
        </button>
      ) : null}
    </PanelFrame>
  );
}
