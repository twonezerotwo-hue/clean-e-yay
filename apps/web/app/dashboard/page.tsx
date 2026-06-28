"use client";

import type { ReactNode } from "react";

import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { MockModeBanner } from "@/components/shell/MockModeBanner";
import { AgentNarratorPanel } from "@/components/panels/AgentNarratorPanel";
import { ExecutionReadinessPanel } from "@/components/panels/ExecutionReadinessPanel";
import { TradeTicketPanel } from "@/components/panels/TradeTicketPanel";
import { RiskDurumuPanel } from "@/components/panels/RiskDurumuPanel";
import { TimeframeMatrixPanel } from "@/components/panels/TimeframeMatrixPanel";
import { AgentMatrixPanel } from "@/components/panels/AgentMatrixPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";
import { AgentBriefPanel } from "@/components/panels/AgentBriefPanel";
import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { DrawdownGuardPanel } from "@/components/panels/DrawdownGuardPanel";
import { PaperActionPanel } from "@/components/panels/PaperActionPanel";
import { MarketSessionsPanel } from "@/components/panels/MarketSessionsPanel";
import { WatchConditionsPanel } from "@/components/panels/WatchConditionsPanel";
import { DecisionTracePanel } from "@/components/panels/DecisionTracePanel";
import { AgentVotesPanel } from "@/components/panels/AgentVotesPanel";
import { ShadowPanel } from "@/components/panels/ShadowPanel";
import { CommandSignalsPanel } from "@/components/panels/CommandSignalsPanel";
import { CryptoDerivativesPanel } from "@/components/panels/CryptoDerivativesPanel";
import { VolatilityPanel } from "@/components/panels/VolatilityPanel";
import { OptionsVolPanel } from "@/components/panels/OptionsVolPanel";
import { CorrelationPanel } from "@/components/panels/CorrelationPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { CatalystImpactPanel } from "@/components/panels/CatalystImpactPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { TradingPanel } from "@/components/panels/TradingPanel";
import { LearningPanel } from "@/components/panels/LearningPanel";
import { WeightProposalPanel } from "@/components/panels/WeightProposalPanel";
import { WeightHistoryPanel } from "@/components/panels/WeightHistoryPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { MistakeMemoryPanel } from "@/components/panels/MistakeMemoryPanel";
import { TfWeightsPanel } from "@/components/panels/TfWeightsPanel";
import { TfTargetsPanel } from "@/components/panels/TfTargetsPanel";
import { MissedOpportunitiesPanel } from "@/components/panels/MissedOpportunitiesPanel";
import { AgentModePanel } from "@/components/panels/AgentModePanel";
import { GovernorPanel } from "@/components/panels/GovernorPanel";
import { ProposalPanel } from "@/components/panels/ProposalPanel";
import { TaskQueuePanel } from "@/components/panels/TaskQueuePanel";
import { DataQualityPanel } from "@/components/panels/DataQualityPanel";
import { ProviderStatusPanel } from "@/components/panels/ProviderStatusPanel";
import { SnapshotPanel } from "@/components/panels/SnapshotPanel";
import { MarketDataPanel } from "@/components/panels/MarketDataPanel";
import { PanelAuditPanel } from "@/components/panels/PanelAuditPanel";
import { SystemHealthBar } from "@/components/panels/SystemHealthBar";
import { ReplayStatusPanel } from "@/components/panels/ReplayStatusPanel";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export default function HomePage() {
  useKeyboardShortcuts();

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl tracking-tight">Clean E-yAy</h1>
          <p className="mt-0.5 text-xs text-white/50">
            agent operating cockpit - karar-destek
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs uppercase tracking-widest text-accent-cyan">
            PAPER_ONLY - NO_EXECUTION
          </div>
        </div>
      </header>

      <MockModeBanner />

      <section className="relative overflow-hidden rounded-xl border border-white/10 bg-[#090d12]/82">
        <div className="pointer-events-none absolute inset-0 opacity-[0.12] [background-image:linear-gradient(rgba(255,255,255,0.58)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.58)_1px,transparent_1px)] [background-size:56px_56px]" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-300/30 to-transparent" />
        <div className="relative p-4 sm:p-5">
          <AgentNarratorPanel />
        </div>
      </section>

      <PanelGroup title="Check List" hint="10 kontrol / 30 saniye / read-only">
        <GridCell span="full" lazy={false}><ExecutionReadinessPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Trade Ticket" hint="broker'a manuel girmeden tek-bakis kart">
        <GridCell span="full" lazy={false}><TradeTicketPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Risk Durumu" hint="ana engel / drawdown / yaklasan olaylar">
        <GridCell span="full" lazy={false}><RiskDurumuPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Karar Matrisi" hint="candidate -> final / TF + agent overlay">
        <GridCell span="full" lazy={false}><TimeframeMatrixPanel /></GridCell>
        <GridCell span="full" lazy={false}><AgentMatrixPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Pozisyon Kontrolleri" hint="acik pozisyon + recheck verdict">
        <GridCell span="full" lazy={false}><PositionChecksPanel /></GridCell>
      </PanelGroup>

      <PanelGroup title="Agent'a Sor" hint="state-grounded / LLM karar vermez">
        <GridCell span="full" lazy={false}><ChatPanel /></GridCell>
      </PanelGroup>

      <section className="space-y-7 rounded-2xl border border-ink-700/60 bg-ink-800/40 px-5 py-5">
        <div className="border-b border-ink-700/50 pb-2">
          <h2 className="text-sm font-medium tracking-wide text-white/80">
            DETAY - Uzman bakisi
          </h2>
          <p className="mt-1 text-xs text-white/40">
            Karar izi, piyasa yapisi, makro, haber, ogrenme ve kalibrasyon panelleri kapali bolum olmadan acik akar.
          </p>
        </div>

        <PanelGroup title="Komuta & Karar" hint="brief / decision / AI rapor / trace / oylama / shadow / adaylar / izleme">
          <GridCell span="full"><AgentBriefPanel /></GridCell>
          <GridCell span="2"><DecisionPanel /></GridCell>
          <GridCell span="1"><AIReportPanel /></GridCell>
          <GridCell span="2"><DecisionTracePanel /></GridCell>
          <GridCell span="1"><AgentVotesPanel /></GridCell>
          <GridCell span="full"><ShadowPanel /></GridCell>
          <GridCell span="full"><CommandSignalsPanel /></GridCell>
          <GridCell span="full"><WatchConditionsPanel /></GridCell>
        </PanelGroup>

        <PanelGroup title="Risk Detayi" hint="Drawdown / Paper Action / Market Sessions">
          <GridCell span="2"><DrawdownGuardPanel /></GridCell>
          <GridCell span="1"><MarketSessionsPanel /></GridCell>
          <GridCell span="full"><PaperActionPanel /></GridCell>
        </PanelGroup>

        <PanelGroup title="Piyasa Yapisi" hint="turev / volatilite / options / korelasyon / rotasyon">
          <GridCell span="1"><CryptoDerivativesPanel /></GridCell>
          <GridCell span="1"><VolatilityPanel /></GridCell>
          <GridCell span="1"><OptionsVolPanel /></GridCell>
          <GridCell span="full"><CorrelationPanel /></GridCell>
          <GridCell span="full" lazy={false}><CapitalRotationPanel /></GridCell>
        </PanelGroup>

        <PanelGroup title="Makro / Catalyst / Haber" hint="haber radari, catalyst etkisi ve olay takvimi ayri paneller olarak acik">
          <GridCell span="full"><NewsPanel /></GridCell>
          <GridCell span="2"><CatalystImpactPanel /></GridCell>
          <GridCell span="1"><EventCalendarPanel /></GridCell>
          <GridCell span="full"><ScenarioPanel /></GridCell>
        </PanelGroup>

        <PanelGroup title="Ogrenme & Kalibrasyon" hint="paper / agirlik / platt / TF kalibrasyon">
          <GridCell span="2"><TradingPanel /></GridCell>
          <GridCell span="1"><LearningPanel /></GridCell>
          <GridCell span="2"><WeightProposalPanel /></GridCell>
          <GridCell span="1"><WeightHistoryPanel /></GridCell>
          <GridCell span="2"><CalibrationPanel /></GridCell>
          <GridCell span="1"><MistakeMemoryPanel /></GridCell>
          <GridCell span="2"><TfWeightsPanel /></GridCell>
          <GridCell span="2"><TfTargetsPanel /></GridCell>
          <GridCell span="2"><MissedOpportunitiesPanel /></GridCell>
          <GridCell span="2"><AgentModePanel /></GridCell>
        </PanelGroup>
      </section>

      <section className="space-y-7 rounded-2xl border border-ink-700/60 bg-ink-800/40 px-5 py-5">
        <div className="border-b border-ink-700/50 pb-2">
          <h2 className="text-sm font-medium tracking-wide text-white/80">
            OPS - Sistem & Veri
          </h2>
          <p className="mt-1 text-xs text-white/40">
            Data quality, provider, system health, replay ve audit panelleri default kapali degil.
          </p>
        </div>

        <PanelGroup title="Data Quality & Providers" hint="veri kalitesi / saglayici / snapshot / piyasa verisi / denetim">
          <GridCell span="2"><DataQualityPanel /></GridCell>
          <GridCell span="1"><ProviderStatusPanel /></GridCell>
          <GridCell span="1"><SnapshotPanel /></GridCell>
          <GridCell span="2"><MarketDataPanel /></GridCell>
          <GridCell span="1"><PanelAuditPanel /></GridCell>
        </PanelGroup>

        <PanelGroup title="System / Replay" hint="sistem sagligi / replay / sozlesme">
          <GridCell span="full"><SystemHealthBar /></GridCell>
          <GridCell span="1"><ReplayStatusPanel /></GridCell>
          <GridCell span="full">
            <p className="text-[10px] text-white/35">
              Sozlesme: <code>contracts/openapi.yaml</code> - tipler codegen ile
              uretilir (tek dogruluk kaynagi).
            </p>
          </GridCell>
        </PanelGroup>
      </section>

      <section className="space-y-7 rounded-2xl border border-ink-700/60 bg-ink-800/40 px-5 py-5">
        <div className="border-b border-ink-700/50 pb-2">
          <h2 className="text-sm font-medium tracking-wide text-white/80">
            GOVERNOR - Oz-Yonetim
          </h2>
          <p className="mt-1 text-xs text-white/40">
            Gozlemler, ogrenir, oneri uretir; owner onayi bekler. Islem acmaz, ayar degistirmez.
          </p>
        </div>

        <PanelGroup title="Governor (Oz-Yonetim)" hint="gozlemler / oneri defteri / gorev kuyrugu — observe-only">
          <GridCell span="full"><GovernorPanel /></GridCell>
          <GridCell span="2"><ProposalPanel /></GridCell>
          <GridCell span="2"><TaskQueuePanel /></GridCell>
        </PanelGroup>
      </section>

      <footer className="pt-8 text-xs text-white/40">
        PAPER_ONLY - NO_EXECUTION - karar-destek; final karar deterministik engine + RiskGate.
      </footer>
    </main>
  );
}

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
