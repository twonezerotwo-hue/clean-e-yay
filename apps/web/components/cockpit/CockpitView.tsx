"use client";

import Link from "next/link";
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
} from "@/lib/selectors/cockpit";

import { AgentBriefingPanel } from "@/components/panels/AgentBriefingPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ExecutionReadinessPanel } from "@/components/panels/ExecutionReadinessPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";

import { HolographicSignalDeck } from "./HolographicSignalDeck";
import { Layer2QuickNav } from "./Layer2QuickNav";
import { MacroRiskStrip } from "./MacroRiskStrip";
import { QuantumBackplaneScene } from "./QuantumBackplaneScene";
import { SpaceBrainScene } from "./SpaceBrainScene";

// Frontend-only information architecture:
// Layer 0: first-screen E-yAy Brain, scanner, conversation.
// Layer 1: six to eight summary surfaces.
// Layer 2: grouped deep panels under /dashboard.
// Layer 3: raw backend/provider/contract spine, read-only.

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

function LayerBadge({ index, label }: { index: string; label: string }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.04] px-3 py-1 text-[10px] uppercase tracking-widest text-white/58">
      <span className="font-display text-accent-cyan">{index}</span>
      <span>{label}</span>
    </div>
  );
}

function LayerHeader({
  index,
  title,
  detail,
  children,
}: {
  index: string;
  title: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-white/[0.08] pb-3 md:flex-row md:items-end md:justify-between">
      <div>
        <LayerBadge index={index} label="katman" />
        <h2 className="mt-3 font-display text-2xl leading-none text-white md:text-3xl">{title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-white/55">{detail}</p>
      </div>
      {children ? <div className="shrink-0">{children}</div> : null}
    </header>
  );
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

function ScanRow({
  label,
  value,
  ok,
  href,
}: {
  label: string;
  value: string;
  ok: boolean;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 transition-colors hover:border-accent-cyan/35 hover:bg-white/[0.055]"
    >
      <span
        className={`h-2.5 w-2.5 rounded-full shadow-[0_0_14px_currentColor] ${
          ok ? "bg-signal-up text-signal-up" : "bg-amber-400 text-amber-400"
        }`}
      />
      <span className="min-w-0">
        <span className="block truncate text-xs text-white/80">{label}</span>
        <span className="block truncate text-[10px] uppercase tracking-widest text-white/35">
          {value}
        </span>
      </span>
      <span className={ok ? "text-[10px] text-signal-up" : "text-[10px] text-amber-300"}>
        {ok ? "OK" : "IZLE"}
      </span>
    </Link>
  );
}

function LayerPortalCard({
  layer,
  title,
  detail,
  href,
}: {
  layer: string;
  title: string;
  detail: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-lg border border-white/10 bg-[#090d12]/76 p-4 transition-colors hover:border-accent-cyan/35 hover:bg-[#0b1118]/90"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-widest text-accent-cyan/70">{layer}</span>
        <span className="text-white/24 transition-colors group-hover:text-accent-cyan">/</span>
      </div>
      <div className="mt-3 font-display text-lg leading-tight text-white/92">{title}</div>
      <p className="mt-2 text-xs leading-5 text-white/52">{detail}</p>
    </Link>
  );
}

function DataSpineCard({
  label,
  value,
  detail,
  href,
  tone = "text-white",
}: {
  label: string;
  value: string;
  detail: string;
  href: string;
  tone?: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-white/10 bg-black/24 p-4 transition-colors hover:border-accent-cyan/35 hover:bg-white/[0.04]"
    >
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-2 font-display text-2xl leading-none ${tone}`}>{value}</div>
      <p className="mt-2 text-xs leading-5 text-white/50">{detail}</p>
    </Link>
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

  const candidates = brief.top_candidates ?? [];
  const activeTicket = ticketList?.tickets?.find((ticket) => ticket.status === "active");
  const dqs = brief.dqs?.score ?? undefined;
  const watch = brief.next_watch_conditions?.slice(0, 3) ?? [];
  const openPaperPositions =
    brief.paper_state_summary?.open_positions ?? brief.open_paper_positions ?? 0;
  const actionableCount = candidates.filter((candidate) => candidate.actionable).length;
  const riskAction = brief.risk?.action ?? "HOLD";
  const riskClear = brief.main_blocker.code !== "RISK_GATE";
  const dataTrusted = brief.data_mode !== "BLOCKED" && (dqs ?? 0) >= 60;
  const decisionTitle = activeTicket
    ? `${activeTicket.symbol} ${activeTicket.side.toUpperCase()}`
    : "Su an islem yok";
  const ticketRr = activeTicket?.summary?.rr_ratio;
  const decisionDetail = activeTicket
    ? `${activeTicket.timeframe} / R:R ${ticketRr != null ? ticketRr.toFixed(2) : "--"} / ${activeTicket.display.confidence_text}`
    : brief.main_blocker.detail ?? brief.main_blocker.label ?? brief.recommended_stance;
  const decisionTone = activeTicket
    ? "text-emerald-200"
    : brief.status === "BLOCKED" || brief.status === "FROZEN"
      ? "text-red-200"
      : "text-amber-200";
  const topSymbols = candidates.length
    ? candidates
        .slice(0, 4)
        .map((candidate) => candidate.symbol ?? "?")
        .join(" / ")
    : "radar bos";

  return (
    <main className="min-h-screen overflow-hidden bg-[#05070b] text-white">
      <section className="relative min-h-screen overflow-hidden border-b border-white/10 bg-[#02030a]">
        <SpaceBrainScene brief={brief} />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_72%_42%,rgba(20,184,166,0.1),transparent_30%),linear-gradient(180deg,rgba(2,3,10,0.28),rgba(2,3,10,0.92))]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#05070b] to-transparent" />

        <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-4 md:py-5">
          <header className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-accent-cyan/35 bg-accent-cyan/10 font-display text-sm text-accent-cyan shadow-[0_0_28px_rgba(34,211,238,0.16)]">
                EY
              </div>
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-widest text-white/42">Katman 0</div>
                <div className="truncate font-display text-sm text-white/86">
                  E-yAy Brain
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

          <div className="grid flex-1 items-center gap-5 py-5 lg:grid-cols-[minmax(0,0.92fr)_minmax(340px,0.58fr)]">
            <section className="max-w-3xl">
              <LayerBadge index="00" label="ilk ekran" />
              <h1 className={`mt-5 max-w-2xl font-display text-4xl leading-[0.98] sm:text-5xl md:text-6xl ${decisionTone}`}>
                {decisionTitle}
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-white/68">{decisionDetail}</p>

              <div className="mt-6 grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
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

              <div className="mt-6 grid gap-2 md:grid-cols-2">
                <ScanRow label="Veri omurgasi" value={`DQS ${formatScore(dqs)} / ${brief.data_mode}`} ok={dataTrusted} href="#layer-3" />
                <ScanRow label="Risk kapisi" value={riskAction} ok={riskClear} href="/dashboard#risk_gate" />
                <ScanRow label="Sinyal adaylari" value={`${actionableCount} actionable / ${candidates.length} izlenen`} ok={actionableCount > 0} href="#layer-1" />
                <ScanRow label="Trade ticket" value={activeTicket ? activeTicket.symbol : "ticket yok"} ok={Boolean(activeTicket)} href="/dashboard#trade_ticket" />
              </div>

              {watch.length ? (
                <div className="mt-5 flex flex-wrap gap-2">
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
            </section>

            <aside className="space-y-3">
              <AgentBriefingPanel />
              <ChatPanel />
            </aside>
          </div>
        </div>
      </section>

      <section
        id="layer-1"
        className="relative overflow-hidden border-t border-white/[0.08] bg-[radial-gradient(circle_at_18%_4%,rgba(167,139,250,0.08),transparent_28%),radial-gradient(circle_at_84%_12%,rgba(251,191,36,0.07),transparent_26%),linear-gradient(180deg,rgba(3,5,12,0.98),rgba(6,8,14,0.99))]"
      >
        <QuantumBackplaneScene brief={brief} />
        <div className="quantum-dashboard-grid pointer-events-none absolute inset-0 z-[1]" />
        <div className="relative z-10 mx-auto max-w-7xl space-y-5 px-4 py-6">
          <LayerHeader
            index="01"
            title="Katman 1 - Ozet Odasi"
            detail="Yazi kalabaligi yerine 6 ana karar yuzeyi: kontrol dongusu, sinyal, makro risk, takvim, senaryo, rotasyon ve haber radari."
          >
            <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
          </LayerHeader>

          <ExecutionReadinessPanel />

          <HolographicSignalDeck brief={brief} />

          <MacroRiskStrip />

          <section className="quantum-panel-cluster grid grid-cols-1 gap-5 xl:grid-cols-2">
            <EventCalendarPanel />
            <ScenarioPanel />
          </section>

          <CapitalRotationPanel />

          <NewsPanel />
        </div>
      </section>

      <section id="layer-2" className="border-t border-white/[0.08] bg-[#05070b]">
        <div className="mx-auto max-w-7xl space-y-5 px-4 py-6">
          <LayerHeader
            index="02"
            title="Katman 2 - Grup Detaylari"
            detail="Katman 1'de ozet gordugun her yuzeyin detayli panel grubu burada. Bu katman okuma ve inceleme icin, emir uretmez."
          />
          <div className="rounded-lg border border-white/10 bg-[#090d12]/72 p-4">
            <Layer2QuickNav />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <LayerPortalCard
              layer="karar"
              title="Decision & Evidence"
              detail="Final durum, ana blocker, karar izi ve agent oy birligi."
              href="/dashboard#decision_trace"
            />
            <LayerPortalCard
              layer="risk"
              title="Risk & Execution"
              detail="RiskGate, drawdown, paper action ve pozisyon kontrolleri."
              href="/dashboard#risk_gate"
            />
            <LayerPortalCard
              layer="piyasa"
              title="Market Structure"
              detail="TF matrisi, korelasyon, volatilite, options, turev ve rotasyon."
              href="/dashboard#correlation"
            />
          </div>
        </div>
      </section>

      <section id="layer-3" className="border-t border-white/[0.08] bg-[#03050a]">
        <div className="mx-auto max-w-7xl space-y-5 px-4 py-6">
          <LayerHeader
            index="03"
            title="Katman 3 - Veri Omurgasi"
            detail="Backendten gelen viewmodel, provider, snapshot ve sistem sagligi burada toplanir. Frontend bu veriyi degistirmez."
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DataSpineCard
              label="Cockpit ViewModel"
              value={AGENT_STATUS_LABEL[brief.status] ?? brief.status}
              detail={`snapshot ${formatGeneratedAt(data?.generated_at)}`}
              href="/dashboard#agent_brief"
              tone={AGENT_STATUS_TONE[brief.status]}
            />
            <DataSpineCard
              label="Data Quality"
              value={`DQS ${formatScore(dqs)}`}
              detail={`mode ${brief.data_mode}`}
              href="/dashboard#data_quality"
              tone={DATA_MODE_TONE[brief.data_mode]}
            />
            <DataSpineCard
              label="Main Blocker"
              value={brief.main_blocker.label}
              detail={brief.main_blocker.detail ?? brief.recommended_stance}
              href="/dashboard#risk_gate"
              tone={BLOCKER_TONE[brief.main_blocker.code]}
            />
            <DataSpineCard
              label="Signal Feed"
              value={topSymbols}
              detail={`${candidates.length} aday / ${actionableCount} actionable`}
              href="/dashboard#agent_matrix"
              tone="text-accent-cyan"
            />
          </div>
        </div>
      </section>
    </main>
  );
}
