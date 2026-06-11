"use client";

import { HeroScene } from "@/components/visuals/HeroScene";
import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { MockModeBanner } from "@/components/shell/MockModeBanner";

import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { RiskGatePanel } from "@/components/panels/RiskGatePanel";
import { AgentVotesPanel } from "@/components/panels/AgentVotesPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";
import { CommandSignalsPanel } from "@/components/panels/CommandSignalsPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { PatternsPanel } from "@/components/panels/PatternsPanel";
import { LearningPanel } from "@/components/panels/LearningPanel";
import { TradingPanel } from "@/components/panels/TradingPanel";
import { ReplayStatusPanel } from "@/components/panels/ReplayStatusPanel";
import { PanelAuditPanel } from "@/components/panels/PanelAuditPanel";
import { SystemHealthBar } from "@/components/panels/SystemHealthBar";
import { DataQualityPanel } from "@/components/panels/DataQualityPanel";
import { ProviderStatusPanel } from "@/components/panels/ProviderStatusPanel";
import { SnapshotPanel } from "@/components/panels/SnapshotPanel";
import { MarketDataPanel } from "@/components/panels/MarketDataPanel";

import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export default function HomePage() {
  useKeyboardShortcuts();
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display tracking-tight">Clean E-yAy</h1>
          <p className="text-xs text-white/50 mt-0.5">
            sözleşme tarafından yönlendirilen karar-destek panosu
          </p>
        </div>
        <div className="text-xs uppercase tracking-widest text-accent-cyan">
          PAPER_ONLY · NO_EXECUTION
        </div>
      </header>

      <MockModeBanner />

      <section className="relative overflow-hidden rounded-2xl border border-ink-700/60 bg-ink-800/70 backdrop-blur min-h-[14rem]">
        <div className="absolute inset-0 -z-10 opacity-70">
          <HeroScene />
        </div>
        <div className="relative p-6">
          <DecisionPanel />
        </div>
      </section>

      <DashboardGrid>
        <GridCell span="2"><DataQualityPanel /></GridCell>
        <GridCell span="1"><ProviderStatusPanel /></GridCell>

        <GridCell span="1"><SnapshotPanel /></GridCell>
        <GridCell span="2"><MarketDataPanel /></GridCell>

        <GridCell span="2"><RiskGatePanel /></GridCell>
        <GridCell span="1"><AgentVotesPanel /></GridCell>

        <GridCell span="3"><PositionChecksPanel /></GridCell>

        <GridCell span="2"><AIReportPanel /></GridCell>
        <GridCell span="1"><ChatPanel /></GridCell>

        <GridCell span="2"><CommandSignalsPanel /></GridCell>
        <GridCell span="1"><EventCalendarPanel /></GridCell>

        <GridCell span="1"><ScenarioPanel /></GridCell>
        <GridCell span="1"><PatternsPanel /></GridCell>
        <GridCell span="1"><ReplayStatusPanel /></GridCell>

        <GridCell span="3"><CapitalRotationPanel /></GridCell>

        <GridCell span="2"><NewsPanel /></GridCell>
        <GridCell span="1"><PanelAuditPanel /></GridCell>

        <GridCell span="2"><LearningPanel /></GridCell>
        <GridCell span="1"><TradingPanel /></GridCell>

        <GridCell span="full"><SystemHealthBar /></GridCell>
      </DashboardGrid>

      <footer className="text-xs text-white/40 pt-8">
        Sözleşme: <code>contracts/openapi.yaml</code> · Tipler codegen ile üretilir.
      </footer>
    </main>
  );
}
