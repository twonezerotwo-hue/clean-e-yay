"use client";

import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import { LoadingState } from "@/components/shell/LoadingState";
import { EmptyState } from "@/components/shell/EmptyState";
import { useCockpitBrief, usePaperTradingState } from "@/lib/queries/hooks";
import { selectAgentBrief } from "@/lib/selectors/cockpit";
import type { Position } from "@/types/generated/api";

// UX1 — paper aksiyon durumu: açık pozisyonlar, süresi dolmuş time-stop'lar,
// yeni giriş kapalı mı / frozen mı, mevcut paper aksiyonu. Negatif geri sayım
// YOK — time-stop durumu backend'de (PaperTradingPanel item 4).

function fmtRemaining(sec: number | null | undefined): string {
  if (sec == null) return "—";
  if (sec <= 0) return "0sn";
  if (sec < 3600) return `${Math.round(sec / 60)}dk`;
  if (sec < 86400) return `${Math.round(sec / 3600)}sa`;
  return `${Math.round(sec / 86400)}g`;
}

function TimeStop({ p }: { p: Position }) {
  // P1 — lifecycle pending durumları önce (fiyat yokken fake kapanış YOK).
  const lc = p.lifecycle_status;
  if (lc === "EXPIRED_PENDING_PRICE" || lc === "EXIT_PENDING") {
    return (
      <span className="text-amber-400" title="exit pending — fiyat gelince kapanır (fake fiyat yok)">
        {p.pending_exit_reason ?? "EXIT"} · fiyat bekleniyor
      </span>
    );
  }
  if (lc === "ERROR_STATE") {
    return <span className="text-signal-down" title="bozuk pozisyon alanları">ERROR_STATE</span>;
  }
  const status = p.time_stop_status ?? (p.valid_until ? "ACTIVE" : "NONE");
  if (status === "NONE") {
    return <span className="text-white/35">time-stop yok</span>;
  }
  if (status === "EXPIRED") {
    return (
      <span className="text-amber-400" title="exit pending — fiyatla TIME_STOP_EXIT'te kapanır">
        TIME_STOP_EXPIRED · exit pending
      </span>
    );
  }
  return (
    <span className="text-white/55 tabular-nums">
      time-stop {fmtRemaining(p.time_stop_seconds_remaining)}
    </span>
  );
}

export function PaperActionPanel() {
  const cockpit = useCockpitBrief();
  const paper = usePaperTradingState();
  if (cockpit.isLoading || paper.isLoading) {
    return (
      <PanelFrame id="paper_action">
        <PanelHeader title="Paper Action State" />
        <LoadingState />
      </PanelFrame>
    );
  }
  const brief = selectAgentBrief(cockpit.data);
  const summary = brief?.paper_state_summary;
  const positions = paper.data?.open_positions ?? [];
  if (!brief && !positions.length) {
    return (
      <PanelFrame id="paper_action">
        <PanelHeader title="Paper Action State" />
        <EmptyState />
      </PanelFrame>
    );
  }
  const actions = summary?.current_paper_actions ?? [];
  const dupWarnings = paper.data?.duplicate_warning ?? [];
  return (
    <PanelFrame id="paper_action">
      <PanelHeader
        title="Paper Action State"
        subtitle="PAPER_ONLY · NO_EXECUTION"
        actions={
          summary?.frozen ? (
            <span className="rounded px-1.5 py-0.5 bg-signal-down/20 text-signal-down uppercase tracking-wide text-[10px]">
              FROZEN
            </span>
          ) : summary?.new_entries_disabled ? (
            <span className="rounded px-1.5 py-0.5 bg-accent-magenta/20 text-accent-magenta uppercase tracking-wide text-[10px]">
              NEW ENTRIES DISABLED
            </span>
          ) : undefined
        }
      />
      <div className="grid grid-cols-2 gap-2 text-xs mb-2">
        <Stat label="Açık pozisyon" value={String(summary?.open_positions ?? positions.length)} />
        <Stat
          label="Süresi dolan time-stop"
          value={String(summary?.expired_time_stops ?? 0)}
          tone={(summary?.expired_time_stops ?? 0) > 0 ? "text-amber-400" : undefined}
        />
      </div>

      {dupWarnings.length ? (
        <div className="mb-2 rounded border border-accent-magenta/40 bg-accent-magenta/10 px-2 py-1 text-[10px] text-accent-magenta">
          DUPLICATE WARNING — aynı symbol+timeframe için birden fazla açık pozisyon
          {dupWarnings.map((w, i) => {
            const r = w as Record<string, unknown>;
            return (
              <span key={i} className="ml-1">
                {String(r.symbol)}/{String(r.timeframe)}×{String(r.open_count)}
              </span>
            );
          })}
        </div>
      ) : null}

      <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
        Mevcut paper aksiyonu
      </div>
      {actions.length ? (
        <ul className="text-[11px] space-y-0.5 mb-2">
          {actions.slice(0, 5).map((a, i) => {
            const r = a as Record<string, unknown>;
            return (
              <li key={i} className="flex justify-between">
                <span className="text-white/70">
                  {String(r.symbol)} {String(r.timeframe)}
                </span>
                <span className="text-signal-up">{String(r.paper_action)}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[11px] text-white/45 mb-2">
          aktif paper aksiyonu yok — {brief?.can_act ? "giriş mümkün" : "yeni giriş kapalı"}
        </p>
      )}

      {positions.length ? (
        <>
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">
            Açık pozisyonlar
          </div>
          <ul className="text-[11px] space-y-0.5">
            {positions.map((p) => (
              <li
                key={p.id}
                className="flex items-center justify-between border-b border-white/5 pb-0.5"
              >
                <span className="flex items-center gap-1.5">
                  <span className="font-medium">{p.symbol}</span>
                  <span className="rounded border border-accent-cyan/40 px-1 text-[9px] uppercase text-accent-cyan">
                    {p.timeframe ?? "1d"}
                  </span>
                  <span className={p.side === "long" ? "text-signal-up" : "text-signal-down"}>
                    {p.side}
                  </span>
                </span>
                <TimeStop p={p} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </PanelFrame>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-white/40">{label}</div>
      <div className={`text-sm ${tone ?? "text-white/90"}`}>{value}</div>
    </div>
  );
}
