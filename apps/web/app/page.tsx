"use client";

import type { ReactNode } from "react";

import { HeroScene } from "@/components/visuals/HeroScene";
import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { MockModeBanner } from "@/components/shell/MockModeBanner";
import { NotificationBell } from "@/components/shell/NotificationBell";
import { NotificationToast } from "@/components/shell/NotificationToast";

// ── ANA — 6 panel (tek-bakış cockpit) ────────────────────────────────────────
import { AgentNarratorPanel } from "@/components/panels/AgentNarratorPanel";
import { TradeTicketPanel } from "@/components/panels/TradeTicketPanel";
import { RiskDurumuPanel } from "@/components/panels/RiskDurumuPanel";
import { TimeframeMatrixPanel } from "@/components/panels/TimeframeMatrixPanel";
import { AgentMatrixPanel } from "@/components/panels/AgentMatrixPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";

// ── DETAY — uzman bakışı (collapsed) ─────────────────────────────────────────
import { AgentBriefPanel } from "@/components/panels/AgentBriefPanel";
import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { RiskGatePanel } from "@/components/panels/RiskGatePanel";
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
import { PatternsPanel } from "@/components/panels/PatternsPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { HaberlerCatalystPanel } from "@/components/panels/HaberlerCatalystPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { TradingPanel } from "@/components/panels/TradingPanel";
import { LearningPanel } from "@/components/panels/LearningPanel";
import { WeightProposalPanel } from "@/components/panels/WeightProposalPanel";
import { WeightHistoryPanel } from "@/components/panels/WeightHistoryPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { MistakeMemoryPanel } from "@/components/panels/MistakeMemoryPanel";
import { TfWeightsPanel } from "@/components/panels/TfWeightsPanel";

// ── OPS — sistem / veri (default kapalı) ─────────────────────────────────────
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
    <main className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display tracking-tight">Clean E-yAy</h1>
          <p className="text-xs text-white/50 mt-0.5">
            agent operating cockpit · karar-destek
          </p>
        </div>
        <div className="flex items-center gap-3">
          <NotificationBell />
          <div className="text-xs uppercase tracking-widest text-accent-cyan">
            PAPER_ONLY · NO_EXECUTION
          </div>
        </div>
      </header>

      <MockModeBanner />

      {/* ──────────────────────────────────────────────────────────────────
          ANA — 6 panel. Broker-action modu için keskin cockpit.
          1) Agent Narrator  2) Trade Ticket  3) Risk Durumu
          4) Karar Matrisi   5) Pozisyon Kontrolleri  6) Agent'a Sor
      ────────────────────────────────────────────────────────────────── */}

      {/* 1) HERO — Agent Narrator (ana sonuç + TF rotator + gündem feed) */}
      <section className="relative overflow-hidden rounded-2xl border border-ink-700/60 bg-ink-800/70 backdrop-blur">
        <div className="absolute inset-0 -z-10 opacity-70">
          <HeroScene />
        </div>
        <div className="relative p-6">
          <AgentNarratorPanel />
        </div>
      </section>

      {/* 2) Trade Ticket */}
      <PanelGroup title="Trade Ticket" hint="broker'a manuel girmeden tek-bakış kart">
        <GridCell span="full"><TradeTicketPanel /></GridCell>
      </PanelGroup>

      {/* 3) Risk Durumu (RiskGate + Drawdown + Catalyst birleşik) */}
      <PanelGroup title="Risk Durumu" hint="ana engel · drawdown · yaklaşan olaylar">
        <GridCell span="full"><RiskDurumuPanel /></GridCell>
      </PanelGroup>

      {/* 4) Karar Matrisi (TF × symbol) */}
      <PanelGroup title="Karar Matrisi" hint="candidate → final · TF + agent overlay">
        <GridCell span="full"><TimeframeMatrixPanel /></GridCell>
        <GridCell span="full"><AgentMatrixPanel /></GridCell>
      </PanelGroup>

      {/* 5) Pozisyon Kontrolleri */}
      <PanelGroup title="Pozisyon Kontrolleri" hint="açık pozisyon + recheck verdict">
        <GridCell span="full"><PositionChecksPanel /></GridCell>
      </PanelGroup>

      {/* 6) Agent'a Sor */}
      <PanelGroup title="Agent'a Sor" hint="state-grounded · LLM karar vermez">
        <GridCell span="full"><ChatPanel /></GridCell>
      </PanelGroup>

      {/* ──────────────────────────────────────────────────────────────────
          DETAY — uzman bakışı. Geri kalan 25 panel collapsed.
      ────────────────────────────────────────────────────────────────── */}
      <details className="group rounded-2xl border border-ink-700/60 bg-ink-800/40">
        <summary className="cursor-pointer select-none list-none px-5 py-3 flex items-center justify-between">
          <span className="text-sm font-medium tracking-wide text-white/80">
            DETAY — Uzman bakışı
          </span>
          <span className="text-xs text-white/40 group-open:hidden">
            karar izi · piyasa yapısı · makro · öğrenme ▾
          </span>
          <span className="text-xs text-white/40 hidden group-open:inline">
            gizle ▴
          </span>
        </summary>
        <div className="px-5 pb-5 pt-1 space-y-7">
          <PanelGroup title="Komuta & Karar" hint="brief · decision · AI rapor · trace · oylama · shadow · adaylar · izleme">
            <GridCell span="full"><AgentBriefPanel /></GridCell>
            <GridCell span="2"><DecisionPanel /></GridCell>
            <GridCell span="1"><AIReportPanel /></GridCell>
            <GridCell span="2"><DecisionTracePanel /></GridCell>
            <GridCell span="1"><AgentVotesPanel /></GridCell>
            <GridCell span="full"><ShadowPanel /></GridCell>
            <GridCell span="full"><CommandSignalsPanel /></GridCell>
            <GridCell span="full"><WatchConditionsPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Risk Detayı" hint="RiskGate · Drawdown · Paper Action · Market Sessions">
            <GridCell span="2"><RiskGatePanel /></GridCell>
            <GridCell span="1"><DrawdownGuardPanel /></GridCell>
            <GridCell span="2"><PaperActionPanel /></GridCell>
            <GridCell span="1"><MarketSessionsPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Piyasa Yapısı" hint="türev · volatilite · options · korelasyon · rotasyon">
            <GridCell span="1"><CryptoDerivativesPanel /></GridCell>
            <GridCell span="1"><VolatilityPanel /></GridCell>
            <GridCell span="1"><OptionsVolPanel /></GridCell>
            <GridCell span="2"><CorrelationPanel /></GridCell>
            <GridCell span="1"><PatternsPanel /></GridCell>
            <GridCell span="full"><CapitalRotationPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Makro / Catalyst" hint="haberler + catalyst + olay takvimi (sekme) · senaryo">
            <GridCell span="full"><HaberlerCatalystPanel /></GridCell>
            <GridCell span="full"><ScenarioPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="Öğrenme & Kalibrasyon" hint="paper · ağırlık · platt · TF kalibrasyon (owner onayı)">
            <GridCell span="2"><TradingPanel /></GridCell>
            <GridCell span="1"><LearningPanel /></GridCell>
            <GridCell span="2"><WeightProposalPanel /></GridCell>
            <GridCell span="1"><WeightHistoryPanel /></GridCell>
            <GridCell span="2"><CalibrationPanel /></GridCell>
            <GridCell span="1"><MistakeMemoryPanel /></GridCell>
            <GridCell span="2"><TfWeightsPanel /></GridCell>
          </PanelGroup>
        </div>
      </details>

      {/* ──────────────────────────────────────────────────────────────────
          OPS — sistem / veri. Default kapalı; sorun olunca açılır.
      ────────────────────────────────────────────────────────────────── */}
      <details className="group rounded-2xl border border-ink-700/60 bg-ink-800/40">
        <summary className="cursor-pointer select-none list-none px-5 py-3 flex items-center justify-between">
          <span className="text-sm font-medium tracking-wide text-white/80">
            OPS — Sistem & Veri
          </span>
          <span className="text-xs text-white/40 group-open:hidden">
            data quality · provider · system health · replay · audit ▾
          </span>
          <span className="text-xs text-white/40 hidden group-open:inline">
            gizle ▴
          </span>
        </summary>
        <div className="px-5 pb-5 pt-1 space-y-7">
          <PanelGroup title="Data Quality & Providers" hint="veri kalitesi · sağlayıcı · snapshot · piyasa verisi · denetim">
            <GridCell span="2"><DataQualityPanel /></GridCell>
            <GridCell span="1"><ProviderStatusPanel /></GridCell>
            <GridCell span="1"><SnapshotPanel /></GridCell>
            <GridCell span="2"><MarketDataPanel /></GridCell>
            <GridCell span="1"><PanelAuditPanel /></GridCell>
          </PanelGroup>

          <PanelGroup title="System / Replay" hint="sistem sağlığı · replay · sözleşme">
            <GridCell span="full"><SystemHealthBar /></GridCell>
            <GridCell span="1"><ReplayStatusPanel /></GridCell>
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
      <NotificationToast />
    </main>
  );
}

// Panelleri okunur IA gruplarına ayıran başlık + grid.
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
