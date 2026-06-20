"use client";

/**
 * Risk Durumu — RiskGate + Drawdown + Catalyst tek panelde 3 bölüm.
 *
 * Mevcut RiskGatePanel + DrawdownGuardPanel + regime_report.event_risk verisini
 * compact biçimde tek kartta sunar. Eski paneller silinmedi — DETAY'da
 * detaylı görünüm için kullanılabilir.
 */
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { useDashboardState, useRegimeReport, useRiskHalts } from "@/lib/queries/hooks";
import {
  selectGauges,
  selectHaltActive,
  selectHaltLevel,
} from "@/lib/selectors/halts";
import { RISK_ACTION_COLOR } from "@/lib/constants";

function StatusRow({
  label,
  value,
  tone,
  detail,
}: {
  label: string;
  value: string;
  tone?: string;
  detail?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-[10px] uppercase tracking-widest text-white/40 shrink-0">{label}</span>
      <div className="text-right min-w-0">
        <div className={`font-mono ${tone ?? "text-white/90"}`}>{value}</div>
        {detail ? <div className="text-[10px] text-white/40 truncate">{detail}</div> : null}
      </div>
    </div>
  );
}

function MiniGauge({ label, ratio, detail }: { label: string; ratio: number; detail: string }) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const tone =
    ratio >= 1 ? "bg-red-400" : ratio >= 0.5 ? "bg-amber-400" : "bg-accent-cyan";
  return (
    <div>
      <div className="flex items-baseline justify-between text-[10px] uppercase tracking-widest text-white/40">
        <span>{label}</span>
        <span className="font-mono text-white/60">{detail}</span>
      </div>
      <div className="mt-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div className={tone} style={{ width: `${clamped * 100}%`, height: "100%" }} />
      </div>
    </div>
  );
}

export function RiskDurumuPanel() {
  const { data: dash, isLoading: dashLoading } = useDashboardState();
  const { data: halts } = useRiskHalts();
  const { data: regime } = useRegimeReport();

  if (dashLoading) {
    return (
      <PanelFrame id="risk_durumu">
        <PanelHeader title="Risk Durumu" subtitle="Risk Kapısı · Drawdown · Catalyst" />
        <LoadingState />
      </PanelFrame>
    );
  }

  const riskGate = dash?.risk_gate;
  const haltActive = selectHaltActive(halts);
  const haltLevel = selectHaltLevel(halts);
  const gauges = selectGauges(halts);
  const eventRisk = (regime as any)?.event_risk;
  const catalysts = (regime as any)?.catalysts ?? [];
  const upcoming = catalysts
    .filter((c: any) => c.minutes_to_event !== undefined && c.minutes_to_event >= 0)
    .sort((a: any, b: any) => a.minutes_to_event - b.minutes_to_event)
    .slice(0, 3);

  // ANA ENGEL özeti (tek satır)
  let blockerText = "Risk kapısı açık · giriş serbest";
  let blockerTone = "text-emerald-300";
  if (riskGate?.action && riskGate.action !== "HOLD") {
    blockerText = `${riskGate.action} — ${riskGate.reason ?? ""}`;
    blockerTone = RISK_ACTION_COLOR[riskGate.action] ?? "text-amber-300";
  }

  return (
    <PanelFrame id="risk_durumu">
      <PanelHeader title="Risk Durumu" subtitle="Risk Kapısı · Drawdown · Catalyst" />
      <div className="space-y-4">
        {/* ── Ana engel banner ── */}
        <div className={`rounded-lg border border-white/10 bg-black/30 px-3 py-2`}>
          <div className="text-[10px] uppercase tracking-widest text-white/40">Ana engel</div>
          <div className={`text-sm font-medium mt-0.5 ${blockerTone}`}>
            {blockerText}
          </div>
        </div>

        {/* ── RiskGate bölümü ── */}
        <section className="space-y-2">
          <div className="text-[11px] font-mono uppercase tracking-widest text-accent-cyan/70 border-b border-white/10 pb-1">
            Risk Kapısı
          </div>
          <StatusRow
            label="Karar"
            value={riskGate?.action ?? "—"}
            tone={RISK_ACTION_COLOR[riskGate?.action ?? ""] ?? "text-white/90"}
            detail={riskGate?.reason}
          />
          {haltActive && haltLevel ? (
            <StatusRow
              label="Halt"
              value={haltLevel}
              tone="text-red-300"
              detail="owner reset gerekli"
            />
          ) : null}
        </section>

        {/* ── Drawdown bölümü ── */}
        <section className="space-y-2">
          <div className="text-[11px] font-mono uppercase tracking-widest text-accent-cyan/70 border-b border-white/10 pb-1">
            Drawdown
          </div>
          <div className="space-y-2">
            <MiniGauge
              label="Günlük zarar"
              ratio={gauges.dailyLossRatio}
              detail={`$${gauges.dailyPnlUsd.toFixed(0)} / -$${Math.abs(gauges.dailyLossLimitUsd).toFixed(0)}`}
            />
            <MiniGauge
              label="Maks. drawdown"
              ratio={gauges.drawdownRatio}
              detail={`${(gauges.drawdownPct * 100).toFixed(1)}% / ${(gauges.maxDrawdownPct * 100).toFixed(0)}%`}
            />
          </div>
        </section>

        {/* ── Catalyst bölümü ── */}
        <section className="space-y-2">
          <div className="text-[11px] font-mono uppercase tracking-widest text-accent-cyan/70 border-b border-white/10 pb-1">
            Yaklaşan olaylar
          </div>
          {eventRisk?.level && eventRisk.level !== "NONE" ? (
            <div className="text-xs text-white/75 leading-snug">
              <span className="text-orange-300">⚠</span> {eventRisk.reason}
            </div>
          ) : null}
          {upcoming.length === 0 ? (
            <p className="text-[11px] text-white/30 italic">Yakında kritik olay yok.</p>
          ) : (
            <ul className="space-y-1">
              {upcoming.map((c: any) => {
                const mins = Math.round(c.minutes_to_event);
                const timeText = mins >= 60 ? `${Math.round(mins / 60)} saat` : `${mins} dk`;
                return (
                  <li key={c.id ?? c.catalyst_id ?? c.title} className="flex items-center justify-between text-xs">
                    <span className="text-white/80 truncate">{c.title ?? c.event_type ?? "—"}</span>
                    <span className="text-[10px] font-mono shrink-0 text-white/50 ml-2">
                      {timeText} · {(c.importance ?? "").toUpperCase()}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </PanelFrame>
  );
}
