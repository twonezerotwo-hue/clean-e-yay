"use client";

import type { ReactNode } from "react";

import { HeroScene } from "@/components/visuals/HeroScene";
import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { MockModeBanner } from "@/components/shell/MockModeBanner";

// UX1 — ilk-ekran cockpit (simple)
import { AgentBriefPanel } from "@/components/panels/AgentBriefPanel";
import { DecisionTracePanel } from "@/components/panels/DecisionTracePanel";
import { WatchConditionsPanel } from "@/components/panels/WatchConditionsPanel";
import { PaperActionPanel } from "@/components/panels/PaperActionPanel";
import { MarketSessionsPanel } from "@/components/panels/MarketSessionsPanel";
import { TimeframeMatrixPanel } from "@/components/panels/TimeframeMatrixPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";

// Uzman / Detaylar (ikinci plan — collapsed)
import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { RiskGatePanel } from "@/components/panels/RiskGatePanel";
import { AgentVotesPanel } from "@/components/panels/AgentVotesPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { CommandSignalsPanel } from "@/components/panels/CommandSignalsPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { CatalystImpactPanel } from "@/components/panels/CatalystImpactPanel";
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
import { WeightProposalPanel } from "@/components/panels/WeightProposalPanel";
import { WeightHistoryPanel } from "@/components/panels/WeightHistoryPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { MistakeMemoryPanel } from "@/components/panels/MistakeMemoryPanel";
import { CorrelationPanel } from "@/components/panels/CorrelationPanel";
import { DrawdownGuardPanel } from "@/components/panels/DrawdownGuardPanel";
import { CryptoDerivativesPanel } from "@/components/panels/CryptoDerivativesPanel";
import { OptionsVolPanel } from "@/components/panels/OptionsVolPanel";
import { VolatilityPanel } from "@/components/panels/VolatilityPanel";

import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export default function HomePage() {
  useKeyboardShortcuts();
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display tracking-tight">Clean E-yAy</h1>
          <p className="text-xs text-white/50 mt-0.5">
            agent operating cockpit · karar-destek
          </p>
        </div>
        <div className="text-xs uppercase tracking-widest text-accent-cyan">
          PAPER_ONLY · NO_EXECUTION
        </div>
      </header>

      <MockModeBanner />

      {/* Agent Command Center — agent'ın beyni, tek bakışta (status / can_act /
          ana engel / aday / izleme). */}
      <section className="relative overflow-hidden rounded-2xl border border-ink-700/60 bg-ink-800/70 backdrop-blur min-h-[14rem]">
        <div className="absolute inset-0 -z-10 opacity-70">
          <HeroScene />
        </div>
        <div className="relative p-6">
          <AgentBriefPanel />
        </div>
      </section>

      {/* SIMPLE — operasyonel cockpit, önem sırasına göre gruplu IA.
          Agent Command Center (hero) → Risk & Execution → Karar İzi → Watch → Chat. */}
      <PanelGroup title="Komuta Merkezi" hint="deterministik karar + analist özeti (neden)">
        <GridCell span="2"><DecisionPanel /></GridCell>
        <GridCell span="1"><AIReportPanel /></GridCell>
      </PanelGroup>

      {/* KILL_SWITCH / HALT varsa: işlem açılamıyorsa ana sebep matristen ÖNCE. */}
      <PanelGroup title="Risk & Yürütme Donması" hint="açamıyorsa ana sebep — matristen önce">
        <GridCell span="2"><RiskGatePanel /></GridCell>
        <GridCell span="1"><DrawdownGuardPanel /></GridCell>
        <GridCell span="2"><PaperActionPanel /></GridCell>
        <GridCell span="1"><PositionChecksPanel /></GridCell>
        <GridCell span="1"><MarketSessionsPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Karar İzi / Aday Matrisi" hint="candidate → final · global gate tek banner">
        <GridCell span="full"><TimeframeMatrixPanel /></GridCell>
        <GridCell span="2"><DecisionTracePanel /></GridCell>
        <GridCell span="1"><AgentVotesPanel /></GridCell>
        <GridCell span="full"><CommandSignalsPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="İzlenecek Koşullar" hint="ne olursa karar değişir">
        <GridCell span="full"><WatchConditionsPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Agent'a Sor" hint="state-grounded · LLM karar vermez">
        <GridCell span="full"><ChatPanel /></GridCell>
      </PanelGroup>

      {/* EXPERT — gruplu detay, varsayılan kapalı. Yalnızca frontend IA düzeni;
          backend/selector/karar mantığı değişmez. */}
      <details className="group rounded-2xl border border-ink-700/60 bg-ink-800/40">
        <summary className="cursor-pointer select-none list-none px-5 py-3 flex items-center justify-between">
          <span className="text-sm font-medium tracking-wide text-white/80">
            Uzman / Detaylar
          </span>
          <span className="text-xs text-white/40 group-open:hidden">
            tüm uzman panellerini göster ▾
          </span>
          <span className="text-xs text-white/40 hidden group-open:inline">
            gizle ▴
          </span>
        </summary>
        <div className="px-5 pb-5 pt-1 space-y-7">
          <PanelGroup title="Data Quality & Providers" hint="veri kalitesi · sağlayıcı · snapshot · denetim">
            <GridCell span="2"><DataQualityPanel /></GridCell>
            <GridCell span="1"><ProviderStatusPanel /></GridCell>
            <GridCell span="1"><SnapshotPanel /></GridCell>
            <GridCell span="2"><MarketDataPanel /></GridCell>
            <GridCell span="1"><PanelAuditPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Market Structure" hint="türev · volatilite · options · korelasyon · rotasyon">
            <GridCell span="1"><CryptoDerivativesPanel /></GridCell>
            <GridCell span="1"><VolatilityPanel /></GridCell>
            <GridCell span="1"><OptionsVolPanel /></GridCell>
            <GridCell span="2"><CorrelationPanel /></GridCell>
            <GridCell span="1"><PatternsPanel /></GridCell>
            <GridCell span="full"><CapitalRotationPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Macro / Catalyst" hint="catalyst etkisi önce · takvim · ham haber · senaryo">
            <GridCell span="2"><CatalystImpactPanel /></GridCell>
            <GridCell span="1"><EventCalendarPanel /></GridCell>
            <GridCell span="2"><NewsPanel /></GridCell>
            <GridCell span="1"><ScenarioPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Paper & Learning" hint="paper trading · öğrenme · ağırlık · kalibrasyon (owner onayı)">
            <GridCell span="2"><TradingPanel /></GridCell>
            <GridCell span="1"><LearningPanel /></GridCell>
            <GridCell span="2"><WeightProposalPanel /></GridCell>
            <GridCell span="1"><WeightHistoryPanel /></GridCell>
            <GridCell span="2"><CalibrationPanel /></GridCell>
            <GridCell span="1"><MistakeMemoryPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Ops / System" hint="replay · sistem sağlığı · sözleşme">
            <GridCell span="1"><ReplayStatusPanel /></GridCell>
            <GridCell span="full"><SystemHealthBar /></GridCell>
            <GridCell span="full">
              <p className="text-[10px] text-white/35">
                Sözleşme: <code>contracts/openapi.yaml</code> — tipler codegen ile
                üretilir (tek doğruluk kaynağı).
              </p>
            </GridCell>
          </PanelGroup>
        </div>
      </details>

      <footer className="text-xs text-white/40 pt-8">
        PAPER_ONLY · NO_EXECUTION — karar-destek; final karar deterministik engine + RiskGate.
      </footer>
    </main>
  );
}

// Panelleri okunur IA gruplarına ayıran başlık + grid (simple ve expert ortak).
function PanelGroup({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-3 border-b border-ink-700/50 pb-1.5">
        <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-white/70">
          {title}
        </h3>
        {hint ? <span className="text-[10px] text-white/35">{hint}</span> : null}
      </div>
      <DashboardGrid>{children}</DashboardGrid>
    </section>
  );
}
