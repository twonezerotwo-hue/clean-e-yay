"use client";

import type { ReactNode } from "react";

import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCockpitBrief } from "@/lib/queries/hooks";
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
import { SpaceBrainScene } from "./SpaceBrainScene";

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
    <div className="min-h-[72px] rounded-lg border border-white/10 bg-black/28 px-3 py-2 backdrop-blur-md">
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
    <section className="rounded-lg border border-white/12 bg-black/34 p-3 shadow-[0_0_34px_rgba(34,211,238,0.08)] backdrop-blur-md">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-widest text-accent-cyan/70">{eyebrow}</span>
        <span className="h-1.5 w-1.5 rounded-full bg-accent-lime shadow-[0_0_12px_rgba(163,230,53,0.9)]" />
      </div>
      <div className="mt-1 font-display text-sm text-white/90">{title}</div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function CockpitView() {
  const { data, isLoading } = useCockpitBrief();

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

  return (
    <main className="min-h-screen overflow-hidden bg-[#02030a] text-white">
      <section className="relative min-h-[620px] overflow-hidden border-b border-white/10 md:min-h-[670px]">
        <SpaceBrainScene brief={brief} />

        <div className="pointer-events-none relative z-10 mx-auto flex min-h-[620px] max-w-7xl flex-col px-4 py-4 md:min-h-[670px] md:py-5">
          <header className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-accent-cyan/35 bg-accent-cyan/10 text-sm shadow-[0_0_22px_rgba(34,211,238,0.22)]">
                AI
              </div>
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-widest text-white/42">
                  Clean E-yAy Cockpit
                </div>
                <div className="truncate font-display text-sm text-white/86">
                  Layer 1 / Agent Brain Command
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="hidden rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[10px] uppercase tracking-widest text-emerald-300 sm:inline-flex">
                Read only
              </span>
              <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-2 py-1 text-[10px] uppercase tracking-widest text-amber-300">
                No execution
              </span>
            </div>
          </header>

          <div className="grid flex-1 items-start gap-4 py-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.52fr)] lg:items-center lg:gap-5 lg:py-5">
            <section className="max-w-2xl">
              <div className="inline-flex rounded-full border border-accent-cyan/24 bg-black/30 px-3 py-1 text-[10px] uppercase tracking-widest text-accent-cyan/80 backdrop-blur-md">
                Space AI Agent Brain / backend viewmodel
              </div>
              <h1 className="mt-4 max-w-xl font-display text-3xl leading-[1.04] text-white sm:text-4xl md:text-5xl">
                Uzay yapay zeka agent beyni
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-6 text-white/76">{brief.summary}</p>

              <div className="mt-5 grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
                <HudMetric
                  label="Agent state"
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
                <HudMetric label="Aday radar" value={String(candidates.length)} tone="text-accent-cyan" />
                <HudMetric label="Paper pozisyon" value={String(openPaperPositions)} tone="text-accent-lime" />
              </div>
            </section>

            <aside className="pointer-events-auto space-y-3">
              <HudPanel eyebrow="Core" title="Karar cekirdegi">
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

              <HudPanel eyebrow="Gate" title="Risk ve ana blokaj">
                <div className={`font-display text-lg ${BLOCKER_TONE[brief.main_blocker.code]}`}>
                  {brief.main_blocker.label}
                </div>
                <p className="mt-1 text-xs leading-5 text-white/62">
                  {brief.main_blocker.detail ?? brief.recommended_stance}
                </p>
              </HudPanel>

              <div className="hidden md:block">
                <HudPanel eyebrow="Radar" title={topSymbols}>
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

          <div className="pointer-events-auto mt-auto hidden md:block">
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
