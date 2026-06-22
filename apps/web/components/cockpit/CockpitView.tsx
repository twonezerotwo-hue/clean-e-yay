"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";

import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { useCockpitBrief, usePaperTradingState, useTradeTickets } from "@/lib/queries/hooks";
import {
  AGENT_STATUS_LABEL,
  AGENT_STATUS_TONE,
  BLOCKER_TONE,
  DATA_MODE_TONE,
  selectAgentBrief,
} from "@/lib/selectors/cockpit";

import { AgentBriefPanel } from "@/components/panels/AgentBriefPanel";
import { AgentMatrixPanel } from "@/components/panels/AgentMatrixPanel";
import { AgentVotesPanel } from "@/components/panels/AgentVotesPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { CommandSignalsPanel } from "@/components/panels/CommandSignalsPanel";
import { CorrelationPanel } from "@/components/panels/CorrelationPanel";
import { CryptoDerivativesPanel } from "@/components/panels/CryptoDerivativesPanel";
import { DataQualityPanel } from "@/components/panels/DataQualityPanel";
import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { DecisionTracePanel } from "@/components/panels/DecisionTracePanel";
import { DrawdownGuardPanel } from "@/components/panels/DrawdownGuardPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ExecutionReadinessPanel } from "@/components/panels/ExecutionReadinessPanel";
import { CatalystImpactPanel } from "@/components/panels/CatalystImpactPanel";
import { LearningPanel } from "@/components/panels/LearningPanel";
import { MarketDataPanel } from "@/components/panels/MarketDataPanel";
import { MarketSessionsPanel } from "@/components/panels/MarketSessionsPanel";
import { MistakeMemoryPanel } from "@/components/panels/MistakeMemoryPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { OptionsVolPanel } from "@/components/panels/OptionsVolPanel";
import { PanelAuditPanel } from "@/components/panels/PanelAuditPanel";
import { PaperActionPanel } from "@/components/panels/PaperActionPanel";
import { PositionChecksPanel } from "@/components/panels/PositionChecksPanel";
import { ProviderStatusPanel } from "@/components/panels/ProviderStatusPanel";
import { ReplayStatusPanel } from "@/components/panels/ReplayStatusPanel";
import { RiskDurumuPanel } from "@/components/panels/RiskDurumuPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { ShadowPanel } from "@/components/panels/ShadowPanel";
import { SnapshotPanel } from "@/components/panels/SnapshotPanel";
import { SystemHealthBar } from "@/components/panels/SystemHealthBar";
import { TfWeightsPanel } from "@/components/panels/TfWeightsPanel";
import { TimeframeMatrixPanel } from "@/components/panels/TimeframeMatrixPanel";
import { TradeTicketPanel } from "@/components/panels/TradeTicketPanel";
import { TradingPanel } from "@/components/panels/TradingPanel";
import { VolatilityPanel } from "@/components/panels/VolatilityPanel";
import { WatchConditionsPanel } from "@/components/panels/WatchConditionsPanel";
import { WeightHistoryPanel } from "@/components/panels/WeightHistoryPanel";
import { WeightProposalPanel } from "@/components/panels/WeightProposalPanel";

import { HolographicSignalDeck } from "./HolographicSignalDeck";
import { Layer0ReporterAgent, type Layer0HeroProps } from "./Layer0ReporterAgent";
import { MacroRiskStrip } from "./MacroRiskStrip";
import { QuantumBackplaneScene } from "./QuantumBackplaneScene";
import { SpaceBrainScene } from "./SpaceBrainScene";

// Frontend-only information architecture:
// Layer 0: first-screen E-yAy Brain, scanner, conversation.
// Layer 1: six to eight summary surfaces.
// Layer 2: grouped deep panels under /dashboard.
// Layer 3: raw backend/provider/contract spine, read-only.

type LayerIndex = 0 | 1 | 2 | 3;

type LayerMeta = {
  index: LayerIndex;
  code: string;
  title: string;
  shortTitle: string;
  subtitle: string;
  depth: string;
};

const LAYERS: LayerMeta[] = [
  {
    index: 0,
    code: "00",
    title: "E-yAy Brain",
    shortTitle: "Brain",
    subtitle: "ilk acilis / kendi kendine tarama / iletisim",
    depth: "dis yuzey",
  },
  {
    index: 1,
    code: "01",
    title: "Ozet Odasi",
    shortTitle: "Ozet",
    subtitle: "6 ana karar yuzeyi / operasyon bakisi",
    depth: "operasyon odasi",
  },
  {
    index: 2,
    code: "02",
    title: "Grup Detaylari",
    shortTitle: "Detay",
    subtitle: "kanit, risk, piyasa yapisi ve analiz gruplari",
    depth: "analiz cekirdegi",
  },
  {
    index: 3,
    code: "03",
    title: "Veri Omurgasi",
    shortTitle: "Veri",
    subtitle: "backend viewmodel / provider / snapshot / sistem sagligi",
    depth: "makine odasi",
  },
];

function parseLayerHash(hash: string): LayerIndex | null {
  const match = hash.match(/layer-(\d)/);
  const value = match ? Number(match[1]) : NaN;
  return value >= 0 && value <= 3 ? (value as LayerIndex) : null;
}

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
  meta,
  detail,
  children,
}: {
  meta: LayerMeta;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-white/[0.08] pb-3 md:flex-row md:items-end md:justify-between">
      <div>
        <LayerBadge index={meta.code} label={meta.depth} />
        <h2 className="mt-3 font-display text-2xl leading-none text-white md:text-3xl">
          Katman {meta.index} - {meta.title}
        </h2>
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

function Layer2DetailGroup({
  index,
  title,
  detail,
  children,
}: {
  index: string;
  title: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <section className="layer2-detail-group">
      <div className="layer2-detail-scan" />
      <header className="relative z-10 mb-4 flex flex-col gap-3 border-b border-white/[0.08] pb-3 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="layer2-detail-index">{index}</span>
            <div className="h-px flex-1 bg-gradient-to-r from-accent-cyan/45 via-white/10 to-transparent" />
          </div>
          <h3 className="mt-3 font-display text-xl leading-none text-white/92 md:text-2xl">
            {title}
          </h3>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-white/52">{detail}</p>
        </div>
        <span className="shrink-0 rounded-full border border-accent-cyan/20 bg-accent-cyan/8 px-3 py-1 text-[10px] uppercase tracking-widest text-accent-cyan/72">
          read-only
        </span>
      </header>
      <div className="relative z-10">{children}</div>
    </section>
  );
}

function DataSpineCard({
  label,
  value,
  detail,
  tone = "text-white",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/24 p-4">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-2 font-display text-2xl leading-none ${tone}`}>{value}</div>
      <p className="mt-2 text-xs leading-5 text-white/50">{detail}</p>
    </div>
  );
}

function LayerRail({
  activeLayer,
  onSelect,
}: {
  activeLayer: LayerIndex;
  onSelect: (layer: LayerIndex) => void;
}) {
  return (
    <nav className="pointer-events-auto fixed left-4 top-1/2 z-40 hidden -translate-y-1/2 xl:block">
      <div className="rounded-full border border-white/10 bg-black/34 p-2 shadow-[0_22px_70px_rgba(0,0,0,0.34)] backdrop-blur-xl">
        <div className="flex flex-col gap-2">
          {LAYERS.map((layer) => {
            const active = layer.index === activeLayer;
            return (
              <button
                key={layer.code}
                type="button"
                onClick={() => onSelect(layer.index)}
                className={`group flex w-[92px] items-center gap-2 rounded-full border px-2 py-2 text-left transition-all ${
                  active
                    ? "border-accent-cyan/55 bg-accent-cyan/12 text-white shadow-[0_0_22px_rgba(34,211,238,0.18)]"
                    : "border-white/8 bg-white/[0.025] text-white/46 hover:border-white/18 hover:text-white/75"
                }`}
                aria-current={active ? "page" : undefined}
              >
                <span className="font-display text-xs text-accent-cyan">{layer.code}</span>
                <span className="text-[10px] uppercase tracking-widest">{layer.shortTitle}</span>
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

function LayerControls({
  activeLayer,
  onSelect,
}: {
  activeLayer: LayerIndex;
  onSelect: (layer: LayerIndex) => void;
}) {
  const previous = activeLayer > 0 ? ((activeLayer - 1) as LayerIndex) : null;
  const next = activeLayer < 3 ? ((activeLayer + 1) as LayerIndex) : null;

  return (
    <div className="pointer-events-auto fixed bottom-12 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/10 bg-black/40 p-2 shadow-[0_22px_70px_rgba(0,0,0,0.34)] backdrop-blur-xl">
      <button
        type="button"
        disabled={previous == null}
        onClick={() => previous != null && onSelect(previous)}
        className="rounded-full border border-white/10 px-3 py-2 text-xs text-white/62 transition-colors hover:border-white/24 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
      >
        Geri
      </button>
      <div className="hidden items-center gap-1 sm:flex">
        {LAYERS.map((layer) => (
          <button
            key={layer.code}
            type="button"
            onClick={() => onSelect(layer.index)}
            className={`h-2.5 rounded-full transition-all ${
              layer.index === activeLayer
                ? "w-8 bg-accent-cyan"
                : "w-2.5 bg-white/24 hover:bg-white/45"
            }`}
            aria-label={`Katman ${layer.index}`}
          />
        ))}
      </div>
      <button
        type="button"
        disabled={next == null}
        onClick={() => next != null && onSelect(next)}
        className="rounded-full border border-accent-cyan/35 bg-accent-cyan/8 px-3 py-2 text-xs text-accent-cyan transition-colors hover:bg-accent-cyan/14 disabled:cursor-not-allowed disabled:opacity-30"
      >
        Iceri gir
      </button>
    </div>
  );
}

function LayerDepthBackdrop({
  activeLayer,
  brief,
}: {
  activeLayer: LayerIndex;
  brief: NonNullable<ReturnType<typeof selectAgentBrief>>;
}) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute inset-0"
        animate={{
          scale: 1 + activeLayer * 0.12,
          opacity: activeLayer === 0 ? 1 : 0.56,
          filter: activeLayer >= 2 ? "blur(5px)" : "blur(0px)",
        }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      >
        <SpaceBrainScene brief={brief} />
      </motion.div>
      <motion.div
        className="absolute inset-0"
        animate={{ opacity: activeLayer === 0 ? 0 : 0.78, scale: 0.98 + activeLayer * 0.04 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      >
        <QuantumBackplaneScene brief={brief} />
      </motion.div>
      <motion.div
        className="absolute inset-0 bg-[radial-gradient(circle_at_58%_46%,rgba(20,184,166,0.13),transparent_26%),radial-gradient(circle_at_72%_16%,rgba(251,191,36,0.09),transparent_23%),linear-gradient(180deg,rgba(2,3,10,0.2),rgba(2,3,10,0.92))]"
        animate={{ opacity: 0.58 + activeLayer * 0.1 }}
      />
      <motion.div
        className="absolute inset-0 opacity-[0.16] [background-image:linear-gradient(rgba(255,255,255,0.58)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.58)_1px,transparent_1px)] [background-size:58px_58px]"
        animate={{ scale: 1 + activeLayer * 0.04, opacity: activeLayer >= 2 ? 0.22 : 0.12 }}
      />
    </div>
  );
}

function LayerStage({
  activeLayer,
  direction,
  children,
}: {
  activeLayer: LayerIndex;
  direction: number;
  children: ReactNode;
}) {
  return (
    <div
      className="relative z-10 mx-auto h-screen max-w-7xl px-4 pb-20 pt-[68px] md:px-6 md:pb-20 md:pt-[72px] xl:pl-24"
      style={{ perspective: 1800 }}
    >
      <motion.section
        key={activeLayer}
        initial={{
          opacity: 0,
          scale: direction >= 0 ? 1.16 : 0.84,
          z: direction >= 0 ? -360 : 260,
          rotateX: direction >= 0 ? 7 : -5,
          filter: "blur(18px)",
        }}
        animate={{
          opacity: 1,
          scale: 1,
          z: 0,
          rotateX: 0,
          filter: "blur(0px)",
        }}
        transition={{ duration: 0.58, ease: [0.22, 1, 0.36, 1] }}
        className="h-full overflow-hidden rounded-2xl border border-white/10 bg-[#05080d]/58 shadow-[0_28px_90px_rgba(0,0,0,0.36)] backdrop-blur-md"
        style={{ transformStyle: "preserve-3d" }}
      >
        {children}
      </motion.section>
    </div>
  );
}

export function CockpitView() {
  const { data, isLoading } = useCockpitBrief();
  const { data: ticketList } = useTradeTickets();
  const { data: paperState } = usePaperTradingState();
  const [activeLayer, setActiveLayer] = useState<LayerIndex>(0);
  const [direction, setDirection] = useState(1);

  const activateLayer = (next: LayerIndex) => {
    setDirection(next >= activeLayer ? 1 : -1);
    setActiveLayer(next);
  };

  useEffect(() => {
    const applyHash = () => {
      const fromHash = parseLayerHash(window.location.hash);
      if (fromHash != null) {
        setActiveLayer((current) => {
          if (fromHash === current) return current;
          setDirection(fromHash > current ? 1 : -1);
          return fromHash;
        });
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  useEffect(() => {
    const nextHash = `#layer-${activeLayer}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
    }
  }, [activeLayer]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable='true']")) return;
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const next = Math.min(3, Math.max(0, activeLayer + delta)) as LayerIndex;
      if (next !== activeLayer) activateLayer(next);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeLayer]);

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
  const ticketRr = activeTicket?.summary?.rr_ratio;
  const unrealizedPnl = paperState?.unrealized_pnl_usd ?? 0;
  const hasOpenPositions = openPaperPositions > 0;
  const newSignalNote = activeTicket
    ? `yeni sinyal: ${activeTicket.symbol} ${activeTicket.side.toUpperCase()}`
    : null;
  // Hero "ilk ekran": canlı portföy önce. Açık pozisyon varsa onları göster
  // (aktif ticket = broker'a devredilecek YENİ sinyal; ayrı kavram, detayda not).
  const decisionTitle = hasOpenPositions
    ? `${openPaperPositions} acik islem`
    : activeTicket
      ? `${activeTicket.symbol} ${activeTicket.side.toUpperCase()}`
      : "Su an islem yok";
  const decisionDetail = hasOpenPositions
    ? [
        `Acik P&L ${unrealizedPnl >= 0 ? "+" : ""}$${Math.round(unrealizedPnl).toLocaleString()}`,
        newSignalNote,
      ]
        .filter(Boolean)
        .join(" / ")
    : activeTicket
      ? `${activeTicket.timeframe} / R:R ${ticketRr != null ? ticketRr.toFixed(2) : "--"} / ${activeTicket.display.confidence_text}`
      : brief.main_blocker.detail ?? brief.main_blocker.label ?? brief.recommended_stance;
  const decisionTone = hasOpenPositions
    ? unrealizedPnl >= 0
      ? "text-emerald-200"
      : "text-red-200"
    : activeTicket
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

  const currentMeta = LAYERS[activeLayer];
  let layerContent: ReactNode;
  const dqsTone =
    (dqs ?? 0) >= 80 ? "text-signal-up" : (dqs ?? 0) >= 60 ? "text-amber-300" : "text-signal-down";
  const heroProps: Layer0HeroProps = {
    title: decisionTitle,
    detail: decisionDetail,
    tone: decisionTone,
    status: {
      label: AGENT_STATUS_LABEL[brief.status] ?? brief.status,
      tone: AGENT_STATUS_TONE[brief.status],
    },
    dqs: { value: formatScore(dqs), tone: dqsTone },
    candidates: candidates.length,
    positions: openPaperPositions,
    scans: {
      veri: {
        label: "Veri omurgasi",
        value: `DQS ${formatScore(dqs)} / ${brief.data_mode}`,
        ok: dataTrusted,
      },
      risk: {
        label: "Risk kapisi",
        value: riskAction,
        ok: riskClear,
        href: "/dashboard#risk_gate",
      },
      sinyal: {
        label: "Sinyal adaylari",
        value: `${actionableCount} actionable / ${candidates.length} izlenen`,
        ok: actionableCount > 0,
      },
      ticket: {
        label: "Trade ticket",
        value: activeTicket ? activeTicket.symbol : "ticket yok",
        ok: Boolean(activeTicket),
        href: "/dashboard#trade_ticket",
      },
    },
    watch: watch.map((item) => ({ key: item.key, label: item.label })),
  };

  if (activeLayer === 0) {
    layerContent = (
      <div className="h-full overflow-hidden p-3 md:p-4">
        <Layer0ReporterAgent hero={heroProps} onNavigate={activateLayer} />
      </div>
      );
  } else if (activeLayer === 1) {
    layerContent = (
        <div className="h-full overflow-y-auto p-4 md:p-5">
          <div className="space-y-5">
            <LayerHeader
              meta={LAYERS[1]}
              detail="Yazi kalabaligi yerine ana karar yuzeyleri: kontrol dongusu, sinyal, makro risk, takvim, senaryo, rotasyon ve haber radari."
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
        </div>
      );
  } else if (activeLayer === 2) {
    layerContent = (
        <div className="h-full overflow-y-auto p-4 md:p-5">
          <div className="space-y-6 pb-12">
            <LayerHeader
              meta={LAYERS[2]}
              detail="Tum detay panelleri link veya tab olmadan burada acik durur. Bu katman okuma ve inceleme icin, emir uretmez."
            >
              <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
            </LayerHeader>

            <div className="layer2-command-strip grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HudMetric label="Grup" value="7" tone="text-accent-cyan" />
              <HudMetric
                label="Sinyal"
                value={`${actionableCount}/${candidates.length}`}
                tone={actionableCount > 0 ? "text-signal-up" : "text-amber-300"}
              />
              <HudMetric
                label="Risk"
                value={riskAction}
                tone={riskClear ? "text-signal-up" : "text-signal-down"}
              />
              <HudMetric
                label="Veri"
                value={`DQS ${formatScore(dqs)}`}
                tone={DATA_MODE_TONE[brief.data_mode]}
              />
            </div>

            <Layer2DetailGroup
              index="01"
              title="Karar ve Agent Kaniti"
              detail="Agent brief, final karar, AI raporu, karar izi, oy birligi ve shadow karsilastirmasi."
            >
              <DashboardGrid>
                <GridCell span="1">
                  <AgentBriefPanel />
                </GridCell>
                <GridCell span="1">
                  <DecisionPanel />
                </GridCell>
                <GridCell span="1">
                  <AIReportPanel />
                </GridCell>
                <GridCell span="2">
                  <DecisionTracePanel />
                </GridCell>
                <GridCell span="1">
                  <AgentVotesPanel />
                </GridCell>
                <GridCell span="2">
                  <AgentMatrixPanel />
                </GridCell>
                <GridCell span="1">
                  <ShadowPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="02"
              title="Islem ve Risk Kapisi"
              detail="Trade ticket, RiskGate, drawdown guard, paper action, pozisyon kontrolleri ve seans uygunlugu."
            >
              <DashboardGrid>
                <GridCell span="1">
                  <TradeTicketPanel />
                </GridCell>
                <GridCell span="1">
                  <RiskDurumuPanel />
                </GridCell>
                <GridCell span="1">
                  <DrawdownGuardPanel />
                </GridCell>
                <GridCell span="1">
                  <PaperActionPanel />
                </GridCell>
                <GridCell span="1">
                  <PositionChecksPanel />
                </GridCell>
                <GridCell span="1">
                  <MarketSessionsPanel />
                </GridCell>
                <GridCell span="2">
                  <WatchConditionsPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="03"
              title="Sinyal ve Timeframe Yapisi"
              detail="Komut sinyalleri, tum timeframe matrisi ve timeframe agirliklari tek akis icinde."
            >
              <DashboardGrid>
                <GridCell span="full">
                  <CommandSignalsPanel />
                </GridCell>
                <GridCell span="2">
                  <TimeframeMatrixPanel />
                </GridCell>
                <GridCell span="1">
                  <TfWeightsPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="04"
              title="Piyasa Yapisi"
              detail="Turev, volatilite, options, korelasyon ve sermaye rotasyonu panelleri."
            >
              <DashboardGrid>
                <GridCell span="1">
                  <CryptoDerivativesPanel />
                </GridCell>
                <GridCell span="1">
                  <VolatilityPanel />
                </GridCell>
                <GridCell span="1">
                  <OptionsVolPanel />
                </GridCell>
                <GridCell span="2">
                  <CorrelationPanel />
                </GridCell>
                <GridCell span="1">
                  <CapitalRotationPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="05"
              title="Makro, Catalyst ve Haber"
              detail="Haber radari, catalyst etkisi, olay takvimi ve senaryo analizi sekme olmadan ayni okuma sirasi icinde."
            >
              <DashboardGrid>
                <GridCell span="full">
                  <NewsPanel />
                </GridCell>
                <GridCell span="2">
                  <CatalystImpactPanel />
                </GridCell>
                <GridCell span="1">
                  <EventCalendarPanel />
                </GridCell>
                <GridCell span="2">
                  <ScenarioPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="06"
              title="Ogrenme ve Kalibrasyon"
              detail="Paper/trading kaydi, ogrenme durumu, agirlik onerileri, kalibrasyon ve hata hafizasi."
            >
              <DashboardGrid>
                <GridCell span="1">
                  <TradingPanel />
                </GridCell>
                <GridCell span="1">
                  <LearningPanel />
                </GridCell>
                <GridCell span="1">
                  <WeightProposalPanel />
                </GridCell>
                <GridCell span="1">
                  <WeightHistoryPanel />
                </GridCell>
                <GridCell span="1">
                  <CalibrationPanel />
                </GridCell>
                <GridCell span="1">
                  <MistakeMemoryPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="07"
              title="Veri Kalitesi ve Operasyon"
              detail="Provider, snapshot, market data, panel audit, sistem sagligi ve replay durumlari."
            >
              <DashboardGrid>
                <GridCell span="1">
                  <DataQualityPanel />
                </GridCell>
                <GridCell span="1">
                  <ProviderStatusPanel />
                </GridCell>
                <GridCell span="1">
                  <SnapshotPanel />
                </GridCell>
                <GridCell span="1">
                  <MarketDataPanel />
                </GridCell>
                <GridCell span="1">
                  <PanelAuditPanel />
                </GridCell>
                <GridCell span="1">
                  <SystemHealthBar />
                </GridCell>
                <GridCell span="1">
                  <ReplayStatusPanel />
                </GridCell>
              </DashboardGrid>
            </Layer2DetailGroup>
          </div>
        </div>
      );
  } else {
    layerContent = (
      <div className="h-full overflow-y-auto p-4 md:p-5">
        <div className="space-y-5">
          <LayerHeader
            meta={LAYERS[3]}
            detail="Backendten gelen viewmodel, provider, snapshot ve sistem sagligi burada toplanir. Frontend bu veriyi degistirmez."
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <DataSpineCard
              label="Cockpit ViewModel"
              value={AGENT_STATUS_LABEL[brief.status] ?? brief.status}
              detail={`snapshot ${formatGeneratedAt(data?.generated_at)}`}
              tone={AGENT_STATUS_TONE[brief.status]}
            />
            <DataSpineCard
              label="Data Quality"
              value={`DQS ${formatScore(dqs)}`}
              detail={`mode ${brief.data_mode}`}
              tone={DATA_MODE_TONE[brief.data_mode]}
            />
            <DataSpineCard
              label="Main Blocker"
              value={brief.main_blocker.label}
              detail={brief.main_blocker.detail ?? brief.recommended_stance}
              tone={BLOCKER_TONE[brief.main_blocker.code]}
            />
            <DataSpineCard
              label="Signal Feed"
              value={topSymbols}
              detail={`${candidates.length} aday / ${actionableCount} actionable`}
              tone="text-accent-cyan"
            />
          </div>
          <Layer2DetailGroup
            index="A"
            title="ViewModel ve Karar Izleri"
            detail="Katman 3 link listesi degil; backendten gelen agent ozeti, karar izi ve data contract burada dogrudan okunur."
          >
            <DashboardGrid>
              <GridCell span="1">
                <AgentBriefPanel />
              </GridCell>
              <GridCell span="1">
                <DecisionPanel />
              </GridCell>
              <GridCell span="2">
                <DecisionTracePanel />
              </GridCell>
              <GridCell span="1">
                <AgentVotesPanel />
              </GridCell>
              <GridCell span="2">
                <AgentMatrixPanel />
              </GridCell>
            </DashboardGrid>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="B"
            title="Provider, Snapshot ve Data Quality"
            detail="Saglayici durumu, DQS, snapshot ve market data panelleri artik ayri link arkasinda degil."
          >
            <DashboardGrid>
              <GridCell span="1">
                <DataQualityPanel />
              </GridCell>
              <GridCell span="1">
                <ProviderStatusPanel />
              </GridCell>
              <GridCell span="1">
                <SnapshotPanel />
              </GridCell>
              <GridCell span="1">
                <MarketDataPanel />
              </GridCell>
            </DashboardGrid>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="C"
            title="Risk, Execution ve Operasyon"
            detail="Risk kapisi, trade ticket, paper action, sistem sagligi, panel audit ve replay omurgasi tek sayfada acik."
          >
            <DashboardGrid>
              <GridCell span="1">
                <TradeTicketPanel />
              </GridCell>
              <GridCell span="1">
                <RiskDurumuPanel />
              </GridCell>
              <GridCell span="1">
                <PaperActionPanel />
              </GridCell>
              <GridCell span="1">
                <PositionChecksPanel />
              </GridCell>
              <GridCell span="1">
                <SystemHealthBar />
              </GridCell>
              <GridCell span="1">
                <PanelAuditPanel />
              </GridCell>
              <GridCell span="1">
                <ReplayStatusPanel />
              </GridCell>
            </DashboardGrid>
          </Layer2DetailGroup>
        </div>
      </div>
    );
  }

  return (
    <main className="relative h-screen overflow-hidden bg-[#02030a] text-white">
      <LayerDepthBackdrop activeLayer={activeLayer} brief={brief} />

      <div className="pointer-events-none fixed inset-x-0 top-0 z-30 border-b border-white/[0.08] bg-black/24 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5 md:px-6 xl:pl-24">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-accent-cyan/35 bg-accent-cyan/10 font-display text-sm text-accent-cyan shadow-[0_0_28px_rgba(34,211,238,0.16)]">
              EY
            </div>
            <div className="min-w-0">
              <div className="truncate font-display text-sm leading-tight text-white/92">
                E-yAy Brain
              </div>
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/42">
                Human-AI Interface
              </div>
            </div>
          </div>
          <div className="hidden min-w-0 flex-1 justify-center md:flex">
            <div className="truncate rounded-full border border-white/10 bg-white/[0.035] px-4 py-1.5 text-[10px] uppercase tracking-[0.2em] text-white/55">
              {currentMeta.subtitle}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-widest text-white/72 sm:inline-flex">
              <span
                className={`h-1.5 w-1.5 rounded-full shadow-[0_0_10px_currentColor] ${
                  brief.data_mode.startsWith("LIVE")
                    ? "bg-signal-up text-signal-up"
                    : "bg-amber-400 text-amber-400"
                }`}
              />
              {brief.data_mode}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/20 bg-amber-400/8 px-2.5 py-1 text-[10px] uppercase tracking-widest text-amber-300">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shadow-[0_0_10px_currentColor]" />
              No_Execution
            </span>
            <span className="hidden text-right leading-tight md:block">
              <span className="block text-[9px] uppercase tracking-widest text-white/40">
                Sistem saati
              </span>
              <SystemClock />
            </span>
            <button
              type="button"
              onClick={() => activateLayer(3)}
              title="Sistem / veri omurgasi"
              className="pointer-events-auto grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.04] text-white/60 transition-colors hover:border-accent-cyan/35 hover:text-accent-cyan"
            >
              <span className="text-base leading-none">⚙</span>
            </button>
          </div>
        </div>
      </div>

      <LayerRail activeLayer={activeLayer} onSelect={activateLayer} />
      <LayerControls activeLayer={activeLayer} onSelect={activateLayer} />

      <LayerStage activeLayer={activeLayer} direction={direction}>
        {layerContent}
      </LayerStage>

      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 border-t border-white/[0.08] bg-black/30 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-2 md:px-6 xl:pl-24">
          <StatusCell
            label="Baglanti"
            value={brief.data_mode.startsWith("LIVE") ? "CANLI" : brief.data_mode}
            tone={brief.data_mode.startsWith("LIVE") ? "text-signal-up" : "text-amber-300"}
          />
          <StatusCell label="Veri kalitesi" value={`DQS ${formatScore(dqs)}`} tone={dqsTone} />
          <StatusCell
            label="Risk modu"
            value={riskAction}
            tone={riskClear ? "text-signal-up" : "text-signal-down"}
          />
          <StatusCell
            label="Piyasa rejimi"
            value={brief.regime ?? "okunuyor"}
            tone="text-accent-cyan"
          />
          <StatusCell
            label="Pozisyon"
            value={String(openPaperPositions)}
            tone="text-amber-200"
          />
          <StatusCell
            label="Durum"
            value={AGENT_STATUS_LABEL[brief.status] ?? brief.status}
            tone={AGENT_STATUS_TONE[brief.status]}
          />
        </div>
      </div>
    </main>
  );
}

function SystemClock() {
  const [now, setNow] = useState("");
  useEffect(() => {
    const tick = () => {
      setNow(
        new Date().toLocaleTimeString("tr-TR", {
          hour12: false,
          timeZone: "Europe/Istanbul",
        }),
      );
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <span className="font-mono text-xs tabular-nums text-white/82">
      {now} <span className="text-white/40">UTC+3</span>
    </span>
  );
}

function StatusCell({
  label,
  value,
  tone = "text-white",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_10px_currentColor] ${tone}`} />
      <span className="text-[10px] uppercase tracking-widest text-white/40">{label}</span>
      <span className={`text-[11px] font-semibold uppercase tracking-widest tabular-nums ${tone}`}>
        {value}
      </span>
    </div>
  );
}
