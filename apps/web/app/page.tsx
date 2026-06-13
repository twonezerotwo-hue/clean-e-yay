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

      {/* Ana karar kartı: agent'ın beyni, tek bakışta. */}
      <section className="relative overflow-hidden rounded-2xl border border-ink-700/60 bg-ink-800/70 backdrop-blur min-h-[14rem]">
        <div className="absolute inset-0 -z-10 opacity-70">
          <HeroScene />
        </div>
        <div className="relative p-6">
          <AgentBriefPanel />
        </div>
      </section>

      {/* Simple Mode — ilk ekranda yalnızca operasyonel cockpit panelleri. */}
      <DashboardGrid>
        <GridCell span="2"><DecisionTracePanel /></GridCell>
        <GridCell span="1"><WatchConditionsPanel /></GridCell>

        <GridCell span="3"><TimeframeMatrixPanel /></GridCell>

        <GridCell span="2"><PaperActionPanel /></GridCell>
        <GridCell span="1"><ChatPanel /></GridCell>
      </DashboardGrid>

      {/* Expert / Details — ikinci plan, varsayılan kapalı. */}
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
        {/* Gruplu başlıklarla okunur uzman düzeni — yalnızca frontend düzeni,
            backend/selector/karar mantığı değişmez. */}
        <div className="px-5 pb-5 pt-1 space-y-7">
          <ExpertGroup title="Karar & Analiz" hint="deterministik karar + açıklayıcı katman">
            <GridCell span="full"><DecisionPanel /></GridCell>
            <GridCell span="2"><AIReportPanel /></GridCell>
            <GridCell span="1"><AgentVotesPanel /></GridCell>
            <GridCell span="3"><PositionChecksPanel /></GridCell>
            <GridCell span="2"><CommandSignalsPanel /></GridCell>
            <GridCell span="1"><ScenarioPanel /></GridCell>
          </ExpertGroup>

          <ExpertGroup title="Risk" hint="RiskGate finaldir — yalnızca kısıtlar">
            <GridCell span="2"><RiskGatePanel /></GridCell>
            <GridCell span="1"><DrawdownGuardPanel /></GridCell>
            <GridCell span="2"><CorrelationPanel /></GridCell>
          </ExpertGroup>

          <ExpertGroup title="Piyasa Yapısı" hint="volatilite · türev · options · catalyst (yalnızca kısıtlayıcı)">
            <GridCell span="1"><VolatilityPanel /></GridCell>
            <GridCell span="1"><CryptoDerivativesPanel /></GridCell>
            <GridCell span="1"><OptionsVolPanel /></GridCell>
            <GridCell span="2"><CatalystImpactPanel /></GridCell>
            <GridCell span="1"><PatternsPanel /></GridCell>
          </ExpertGroup>

          <ExpertGroup title="Veri" hint="provider · DQS · snapshot · haber · rotasyon">
            <GridCell span="2"><DataQualityPanel /></GridCell>
            <GridCell span="1"><ProviderStatusPanel /></GridCell>
            <GridCell span="1"><SnapshotPanel /></GridCell>
            <GridCell span="2"><MarketDataPanel /></GridCell>
            <GridCell span="3"><CapitalRotationPanel /></GridCell>
            <GridCell span="2"><NewsPanel /></GridCell>
            <GridCell span="1"><EventCalendarPanel /></GridCell>
          </ExpertGroup>

          <ExpertGroup title="Öğrenme" hint="kalibrasyon · mistake memory · ağırlık önerisi (owner onayı)">
            <GridCell span="2"><LearningPanel /></GridCell>
            <GridCell span="1"><TradingPanel /></GridCell>
            <GridCell span="2"><WeightProposalPanel /></GridCell>
            <GridCell span="1"><WeightHistoryPanel /></GridCell>
            <GridCell span="2"><CalibrationPanel /></GridCell>
            <GridCell span="1"><MistakeMemoryPanel /></GridCell>
          </ExpertGroup>

          <ExpertGroup title="Ops" hint="replay · pano denetimi · sistem sağlığı">
            <GridCell span="1"><ReplayStatusPanel /></GridCell>
            <GridCell span="1"><PanelAuditPanel /></GridCell>
            <GridCell span="full"><SystemHealthBar /></GridCell>
          </ExpertGroup>
        </div>
      </details>

      <footer className="text-xs text-white/40 pt-8">
        Sözleşme: <code>contracts/openapi.yaml</code> · Tipler codegen ile üretilir.
      </footer>
    </main>
  );
}

// Uzman bölümünde panelleri okunur alt gruplara ayırır (yalnızca görsel düzen).
function ExpertGroup({
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
