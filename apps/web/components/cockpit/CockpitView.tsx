"use client";

import type { ReactNode } from "react";

import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCockpitBrief, useTradeTickets } from "@/lib/queries/hooks";
import {
  AGENT_STATUS_LABEL,
  AGENT_STATUS_TONE,
  BLOCKER_TONE,
  DATA_MODE_TONE,
  selectAgentBrief,
  selectDecisionTrace,
} from "@/lib/selectors/cockpit";

import { NewsPanel } from "@/components/panels/NewsPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";

import { AgentBrainCard } from "./AgentBrainCard";
import { CockpitCard, buildCockpitCards } from "./cards";
import { HolographicSignalDeck } from "./HolographicSignalDeck";
import { Layer2QuickNav } from "./Layer2QuickNav";
import { MacroRiskStrip } from "./MacroRiskStrip";
import { QuantumBackplaneScene } from "./QuantumBackplaneScene";
import { SignalRadar } from "./SignalRadar";

// Layer 1 reads one backend ViewModel and turns it into a visual cockpit.
// No decisions, orders, live calls, or backend mutations happen here.

function formatGeneratedAt(value?: string) {
  if (!value) return "snapshot bekleniyor";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "snapshot hazir";
  return new Intl.DateTimeFormat("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatScore(value?: number | null) {
  return value == null ? "--" : String(Math.round(value));
}

function HudMetric({
  label,
  value,
  tone = "text-white",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="min-h-[72px] rounded-lg border border-white/10 bg-black/24 px-3 py-2">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-1 font-display text-xl leading-none tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

function HudPanel({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-[#090d12]/78 p-3 shadow-[0_18px_44px_rgba(0,0,0,0.22)]">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-widest text-white/42">{eyebrow}</span>
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-300/80" />
      </div>
      <div className="mt-1 font-display text-sm text-white/90">{title}</div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function CockpitView() {
  const { data, isLoading } = useCockpitBrief();
  const { data: ticketList } = useTradeTickets();

  if (isLoading) {
    return (
      <div className="p-6">
        <LoadingState />
      </div>
    );
  }

  const brief = selectAgentBrief(data);
  if (!brief) {
    return (
      <div className="p-6">
        <EmptyState />
      </div>
    );
  }

  const trace = selectDecisionTrace(data);
  const cards = buildCockpitCards(brief, trace);
  const candidates = brief.top_candidates ?? [];
  const activeTicket = ticketList?.tickets?.find((ticket) => ticket.status === "active");
  const dqs = brief.dqs?.score ?? undefined;
  const watch = brief.next_watch_conditions?.slice(0, 3) ?? [];
  const topSymbols = candidates.length
    ? candidates
        .slice(0, 4)
        .map((candidate) => candidate.symbol ?? "?")
        .join(" / ")
    : "radar bos";
  const openPaperPositions =
    brief.paper_state_summary?.open_positions ?? brief.open_paper_positions ?? 0;
  const decisionTitle = activeTicket
    ? `${activeTicket.symbol} ${activeTicket.side.toUpperCase()}`
    : "Su an islem yok";
  const decisionDetail = activeTicket
    ? `${activeTicket.timeframe} · R:R ${activeTicket.summary.rr_ratio.toFixed(2)} · ${activeTicket.display.confidence_text}`
    : brief.main_blocker.detail ?? brief.main_blocker.label ?? brief.recommended_stance;
  const decisionTone = activeTicket
    ? "text-emerald-200"
    : brief.status === "BLOCKED" || brief.status === "FROZEN"
      ? "text-red-200"
      : "text-amber-200";

  return (
    <main className="min-h-screen overflow-hidden bg-[#05070b] text-white">
      <section className="relative min-h-[520px] overflow-hidden border-b border-white/10 bg-[#070a0f] md:min-h-[560px]">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(9,13,18,0.98),rgba(5,7,11,0.98))]" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(rgba(255,255,255,0.58)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.58)_1px,transparent_1px)] [background-size:64px_64px]" />
        <div className="pointer-events-none absolute left-[7%] top-20 h-px w-[42%] bg-gradient-to-r from-transparent via-emerald-300/30 to-transparent" />
        <div className="pointer-events-none absolute right-[8%] top-28 h-[240px] w-[240px] rounded-full border border-white/[0.06] bg-emerald-400/[0.025]" />
        <div className="pointer-events-none absolute right-[14%] top-44 h-[120px] w-[120px] rounded-full border border-amber-300/[0.08]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#05070b] to-transparent" />

        <div className="relative z-10 mx-auto flex min-h-[520px] max-w-7xl flex-col px-4 py-4 md:min-h-[560px] md:py-5">
          <header className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-emerald-300/28 bg-emerald-300/8 text-xs text-emerald-200">
                CE
              </div>
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-widest text-white/42">
                  Clean E-yAy
                </div>
                <div className="truncate font-display text-sm text-white/86">
                  Karar durumu
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="hidden rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] uppercase tracking-widest text-white/55 sm:inline-flex">
                {brief.data_mode}
              </span>
              <span className="rounded-full border border-amber-400/20 bg-amber-400/8 px-2 py-1 text-[10px] uppercase tracking-widest text-amber-300">
                NO_EXECUTION
              </span>
            </div>
          </header>

          <div className="grid flex-1 items-start gap-4 py-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.52fr)] lg:items-center lg:gap-5">
            <section className="max-w-2xl rounded-lg border border-white/10 bg-[#090d12]/72 p-4 shadow-[0_22px_60px_rgba(0,0,0,0.28)] md:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-widest text-white/52">
                  {AGENT_STATUS_LABEL[brief.status] ?? brief.status}
                </span>
                <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
              </div>
              <h1 className={`mt-5 max-w-xl font-display text-3xl leading-[1.04] sm:text-4xl md:text-5xl ${decisionTone}`}>
                {decisionTitle}
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-white/68">{decisionDetail}</p>

              <div className="mt-5 grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
                <HudMetric
                  label="Durum"
                  value={AGENT_STATUS_LABEL[brief.status] ?? brief.status}
                  tone={AGENT_STATUS_TONE[brief.status]}
                />
                <HudMetric
                  label="DQS"
                  value={formatScore(dqs)}
                  tone={
                    (dqs ?? 0) >= 80
                      ? "text-signal-up"
                      : (dqs ?? 0) >= 60
                        ? "text-amber-300"
                        : "text-signal-down"
                  }
                />
                <HudMetric label="Aday" value={String(candidates.length)} tone="text-emerald-200" />
                <HudMetric label="Pozisyon" value={String(openPaperPositions)} tone="text-amber-200" />
              </div>
            </section>

            <aside className="space-y-3">
              <HudPanel eyebrow="Veri" title="Snapshot">
                <div className="flex items-center justify-between gap-3">
                  <span className={`font-display text-xl ${AGENT_STATUS_TONE[brief.status]}`}>
                    {AGENT_STATUS_LABEL[brief.status] ?? brief.status}
                  </span>
                  <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                  <div className="rounded border border-white/10 bg-white/[0.03] p-2">
                    <div className="uppercase tracking-widest text-white/35">Mod</div>
                    <div className={DATA_MODE_TONE[brief.data_mode]}>{brief.data_mode}</div>
                  </div>
                  <div className="rounded border border-white/10 bg-white/[0.03] p-2">
                    <div className="uppercase tracking-widest text-white/35">Snapshot</div>
                    <div className="text-white/70">{formatGeneratedAt(data?.generated_at)}</div>
                  </div>
                </div>
              </HudPanel>

              <HudPanel eyebrow="Risk" title={brief.main_blocker.label}>
                <div className={`font-display text-lg ${BLOCKER_TONE[brief.main_blocker.code]}`}>
                  {brief.main_blocker.label}
                </div>
                <p className="mt-1 text-xs leading-5 text-white/62">
                  {brief.main_blocker.detail ?? brief.recommended_stance}
                </p>
              </HudPanel>

              <div className="hidden md:block">
                <HudPanel eyebrow="Adaylar" title={topSymbols}>
                  <div className="space-y-1.5">
                    {candidates.slice(0, 4).map((candidate, index) => (
                      <div
                        key={`${candidate.symbol}-${candidate.timeframe}-${index}`}
                        className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-xs"
                      >
                        <span className="truncate font-display text-white/86">{candidate.symbol ?? "--"}</span>
                        <span className="text-white/42">{candidate.direction ?? "neutral"}</span>
                        <span className="tabular-nums text-accent-cyan">
                          {formatScore(candidate.score)}
                        </span>
                      </div>
                    ))}
                    {!candidates.length ? (
                      <div className="rounded border border-white/10 bg-white/[0.03] px-2 py-2 text-xs text-white/45">
                        Izlenen aday yok.
                      </div>
                    ) : null}
                  </div>
                </HudPanel>
              </div>
            </aside>
          </div>

          <div className="mt-auto hidden md:block">
            {watch.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {watch.map((item, index) => (
                  <span
                    key={`${item.key}-${index}`}
                    className="rounded-full border border-white/10 bg-black/28 px-3 py-1 text-[11px] text-white/64 backdrop-blur-md"
                  >
                    {item.label}
                  </span>
                ))}
              </div>
            ) : null}
            <Layer2QuickNav />
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden border-t border-white/[0.08] bg-[radial-gradient(circle_at_18%_4%,rgba(167,139,250,0.08),transparent_28%),radial-gradient(circle_at_84%_12%,rgba(251,191,36,0.07),transparent_26%),linear-gradient(180deg,rgba(3,5,12,0.98),rgba(6,8,14,0.99))]">
        <QuantumBackplaneScene brief={brief} />
        <div className="quantum-dashboard-grid pointer-events-none absolute inset-0 z-[1]" />
        <div className="relative z-10 mx-auto max-w-7xl space-y-5 px-4 py-5">
          <div className="md:hidden">
            <Layer2QuickNav />
          </div>

          <HolographicSignalDeck brief={brief} />

          <MacroRiskStrip />

          <section className="quantum-panel-cluster grid grid-cols-1 gap-5 xl:grid-cols-2">
            <EventCalendarPanel />
            <ScenarioPanel />
          </section>

          <CapitalRotationPanel />

          <AgentBrainCard brief={brief} generatedAt={data?.generated_at} />

          <section className="quantum-panel-cluster quantum-panel-cluster-cards grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cards.map((card) => (
              <CockpitCard key={card.id} {...card} />
            ))}
          </section>

          <NewsPanel />

          <SignalRadar brief={brief} />
        </div>
      </section>
    </main>
  );
}
