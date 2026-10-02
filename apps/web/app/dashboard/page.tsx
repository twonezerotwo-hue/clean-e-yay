"use client";

import type { ReactNode } from "react";

import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { MockModeBanner } from "@/components/shell/MockModeBanner";
import { TabbedBox } from "@/components/shell/TabbedBox";
import { TradeTicketPanel } from "@/components/panels/TradeTicketPanel";
import { RiskDurumuPanel } from "@/components/panels/RiskDurumuPanel";
import { TimeframeMatrixPanel } from "@/components/panels/TimeframeMatrixPanel";
import { AgentMatrixPanel } from "@/components/panels/AgentMatrixPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
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
import { CatalystImpactPanel } from "@/components/panels/CatalystImpactPanel";
import { TradingPanel } from "@/components/panels/TradingPanel";
import { DataQualityPanel } from "@/components/panels/DataQualityPanel";
import { ProviderStatusPanel } from "@/components/panels/ProviderStatusPanel";
import { SnapshotPanel } from "@/components/panels/SnapshotPanel";
import { MarketDataPanel } from "@/components/panels/MarketDataPanel";
import { PanelAuditPanel } from "@/components/panels/PanelAuditPanel";
import { SystemHealthBar } from "@/components/panels/SystemHealthBar";
import { ReplayStatusPanel } from "@/components/panels/ReplayStatusPanel";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

// Detaylar sayfası (owner kararı K8): yalnız katmanlarda (Brain / Heart / Soul /
// Conscious) GÖSTERİLMEYEN durumlar burada. Katmandaki bir panel buraya tekrar
// eklenmez; aynı konudaki paneller sekmeli tek kutuda (TabbedBox) durur.
const SECTIONS = [
  { id: "risk_gate", label: "Risk" },
  { id: "karar", label: "Karar" },
  { id: "pozisyonlar", label: "Pozisyonlar" },
  { id: "piyasa", label: "Piyasa" },
  { id: "sistem", label: "Sistem & Veri" },
] as const;

export default function DetailsPage() {
  useKeyboardShortcuts();

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl tracking-tight">Clean E-yAy · Detaylar</h1>
          <p className="mt-0.5 text-xs text-white/50">
            katmanlarda olmayan durumlar · karar-destek
          </p>
        </div>
        <div className="text-xs uppercase tracking-widest text-accent-cyan">
          PAPER_ONLY · PAPER_AUTO_OPEN · NO_LIVE_EXECUTION
        </div>
      </header>

      <MockModeBanner />

      <nav className="flex flex-wrap items-center gap-1.5 border-b border-ink-700/50 pb-3 text-[10px] uppercase tracking-[0.14em]">
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-white/60 transition hover:border-accent-cyan/45 hover:text-accent-cyan"
          >
            {s.label}
          </a>
        ))}
        <span className="ml-auto normal-case tracking-normal text-white/35">
          Sohbet ve açık pozisyonlar → <a className="text-accent-cyan/80 hover:underline" href="/#layer-0">Brain</a>
          {" · "}checklist, haber, takvim, senaryo, likidite → <a className="text-accent-cyan/80 hover:underline" href="/#layer-1">Heart</a>
          {" · "}dünya özeti → <a className="text-accent-cyan/80 hover:underline" href="/#layer-2">Soul</a>
          {" · "}öğrenme ve kalibrasyon → <a className="text-accent-cyan/80 hover:underline" href="/#layer-3">Conscious</a>
        </span>
      </nav>

      <PanelGroup id="risk_gate" title="Risk" hint="ana engel · paper aksiyon · seanslar · halt geçmişi">
        <GridCell span="full" lazy={false}><RiskDurumuPanel /></GridCell>
        <GridCell span="full" lazy={false}>
          {/* Drawdown çubukları Risk Durumu'nda; Drawdown Guard'ın ek bilgisi halt geçmişi. */}
          <TabbedBox
            tabs={[
              { key: "paper_action", label: "Paper aksiyon", node: <PaperActionPanel /> },
              { key: "sessions", label: "Seanslar", node: <MarketSessionsPanel /> },
              { key: "halts", label: "Halt geçmişi", node: <DrawdownGuardPanel /> },
            ]}
          />
        </GridCell>
      </PanelGroup>

      <PanelGroup id="karar" title="Karar" hint="matris · neden · adaylar · izleme">
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "tf_matrix", label: "Timeframe matrisi", node: <TimeframeMatrixPanel /> },
              { key: "agent_matrix", label: "Agent matrisi", node: <AgentMatrixPanel /> },
            ]}
          />
        </GridCell>
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "decision", label: "Karar merkezi", node: <DecisionPanel /> },
              { key: "trace", label: "Karar izi", node: <DecisionTracePanel /> },
              { key: "votes", label: "Kanıt zinciri", node: <AgentVotesPanel /> },
              { key: "ticket", label: "Sinyal oluşumu", node: <TradeTicketPanel /> },
              { key: "candidates", label: "Adaylar", node: <CommandSignalsPanel /> },
              { key: "watch", label: "İzleme koşulları", node: <WatchConditionsPanel /> },
              { key: "shadow", label: "Gölge", node: <ShadowPanel /> },
            ]}
          />
        </GridCell>
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "ai_report", label: "AI analist raporu", node: <AIReportPanel /> },
              { key: "brief", label: "Agent brief", node: <AgentBriefPanel /> },
            ]}
          />
        </GridCell>
      </PanelGroup>

      <PanelGroup id="pozisyonlar" title="Pozisyonlar" hint="recheck kararı · paper defteri">
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "checks", label: "Kontroller", node: <PositionChecksPanel /> },
              { key: "paper", label: "Paper defteri", node: <TradingPanel /> },
            ]}
          />
        </GridCell>
      </PanelGroup>

      <PanelGroup id="piyasa" title="Piyasa" hint="katalizör · volatilite · korelasyon · türev · opsiyon">
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "catalyst", label: "Katalizör etkisi", node: <CatalystImpactPanel /> },
              { key: "volatility", label: "Volatilite", node: <VolatilityPanel /> },
              { key: "correlation", label: "Korelasyon", node: <CorrelationPanel /> },
              { key: "derivatives", label: "Kripto türevleri", node: <CryptoDerivativesPanel /> },
              { key: "options", label: "Opsiyon IV", node: <OptionsVolPanel /> },
            ]}
          />
        </GridCell>
      </PanelGroup>

      <PanelGroup id="sistem" title="Sistem & Veri" hint="sağlık · veri kalitesi · sağlayıcı · replay">
        <GridCell span="full"><SystemHealthBar /></GridCell>
        <GridCell span="full">
          <TabbedBox
            tabs={[
              { key: "dqs", label: "Veri kalitesi", node: <DataQualityPanel /> },
              { key: "providers", label: "Sağlayıcılar", node: <ProviderStatusPanel /> },
              { key: "snapshot", label: "Snapshot", node: <SnapshotPanel /> },
              { key: "market_data", label: "Piyasa verisi", node: <MarketDataPanel /> },
              { key: "replay", label: "Replay", node: <ReplayStatusPanel /> },
              { key: "audit", label: "Pano denetimi", node: <PanelAuditPanel /> },
            ]}
          />
        </GridCell>
      </PanelGroup>

      <footer className="pt-6 text-xs text-white/40">
        Karar-destek: uygun sinyaller RiskGate sonrası yalnız paper state'e açılır; gerçek broker emri gönderilmez.
      </footer>
    </main>
  );
}

function PanelGroup({
  id,
  title,
  hint,
  children,
}: {
  id: string;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-4 space-y-3">
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
