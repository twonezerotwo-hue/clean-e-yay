"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";

import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
import { DashboardGrid, GridCell } from "@/components/shell/DashboardGrid";
import { EmptyState } from "@/components/shell/EmptyState";
import { LoadingState } from "@/components/shell/LoadingState";
import { PanelFrame } from "@/components/shell/PanelFrame";
import { PanelHeader } from "@/components/shell/PanelHeader";
import {
  useAgentMatrix,
  useCockpitBrief,
  useDashboardState,
  usePaperTradingState,
  useTradeTickets,
} from "@/lib/queries/hooks";
import {
  AGENT_STATUS_LABEL,
  AGENT_STATUS_TONE,
  BLOCKER_TONE,
  DATA_MODE_TONE,
  selectAgentBrief,
} from "@/lib/selectors/cockpit";

import { AgentBriefPanel } from "@/components/panels/AgentBriefPanel";
import { AgentMatrixPanel } from "@/components/panels/AgentMatrixPanel";
import { AgentNarratorPanel } from "@/components/panels/AgentNarratorPanel";
import { AgentVotesPanel } from "@/components/panels/AgentVotesPanel";
import { AIReportPanel } from "@/components/panels/AIReportPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";
import { CommandSignalsPanel } from "@/components/panels/CommandSignalsPanel";
import { CorrelationPanel } from "@/components/panels/CorrelationPanel";
import { CryptoDerivativesPanel } from "@/components/panels/CryptoDerivativesPanel";
import { DataQualityPanel } from "@/components/panels/DataQualityPanel";
import { DecisionPanel } from "@/components/panels/DecisionPanel";
import { DecisionTracePanel } from "@/components/panels/DecisionTracePanel";
import { DrawdownGuardPanel } from "@/components/panels/DrawdownGuardPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ExecutionReadinessPanel } from "@/components/panels/ExecutionReadinessPanel";
import { OrderTicketPanel } from "@/components/panels/OrderTicketPanel";
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
import {
  Layer2AssetDrilldownPanel,
  Layer2AssetUniversePanel,
  Layer2BacktestOutcomePanel,
  Layer2FibonacciLabPanel,
  Layer2SystemBriefArchivePanel,
} from "./Layer2Labs";
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

type Layer1StackItem = {
  key: string;
  node: ReactNode;
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
    title: "Analiz Lableri",
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
  id,
  children,
}: {
  index: string;
  title: string;
  detail: string;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="layer2-detail-group">
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

function MiniStatusLine({
  label,
  value,
  detail,
  tone = "text-white/90",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/24 px-3 py-2 text-xs">
      <span className="shrink-0 text-[10px] uppercase tracking-widest text-white/38">{label}</span>
      <div className="min-w-0 text-right">
        <div className={`font-mono font-semibold ${tone}`}>{value}</div>
        {detail ? <div className="mt-0.5 truncate text-[10px] text-white/42">{detail}</div> : null}
      </div>
    </div>
  );
}

function riskGateTone(action?: string | null) {
  if (action === "HOLD") return "text-emerald-300";
  if (action === "KILL_SWITCH" || action === "RISK_REDUCE") return "text-red-300";
  if (action === "NO_POSITION_INCREASE") return "text-amber-300";
  return "text-white/80";
}

function RiskGateAnchorPanel() {
  const { data, isLoading } = useDashboardState();
  const riskGate = data?.risk_gate;
  return (
    <PanelFrame id="risk_gate">
      <PanelHeader title="Risk Kapisi" subtitle="dashboard#risk_gate karsiligi / read-only" />
      {isLoading ? (
        <LoadingState />
      ) : !riskGate ? (
        <EmptyState message="RiskGate verisi yok." />
      ) : (
        <div className="space-y-2">
          <MiniStatusLine
            label="Karar"
            value={riskGate.action}
            detail={riskGate.reason}
            tone={riskGateTone(riskGate.action)}
          />
          <MiniStatusLine
            label="Durum"
            value={riskGate.action === "HOLD" ? "Yeni girise engel yok" : "Kisitlayici"}
            tone={riskGate.action === "HOLD" ? "text-emerald-300" : riskGateTone(riskGate.action)}
          />
          {riskGate.evidence?.length ? (
            <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
              <div className="text-[10px] uppercase tracking-widest text-white/38">Kanıt</div>
              <div className="mt-1 space-y-1 text-xs leading-5 text-white/58">
                {riskGate.evidence.slice(0, 5).map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </PanelFrame>
  );
}

const PATTERN_LABEL: Record<string, string> = {
  uptrend_structure: "Yukselen yapi",
  downtrend_structure: "Dusen yapi",
  ranging: "Range / yatay",
};

function patternTone(pattern?: string | null) {
  if (pattern === "uptrend_structure") return "text-emerald-300";
  if (pattern === "downtrend_structure") return "text-red-300";
  return "text-white/62";
}

function reversalTone(bias?: string | null) {
  if (bias === "BULLISH") return "text-emerald-300";
  if (bias === "BEARISH") return "text-red-300";
  return "text-white/45";
}

function PatternsAnchorPanel() {
  const { data, isLoading } = useAgentMatrix();
  const rows = data?.symbols ?? [];
  const hasEvidence = rows.some((row) => row.pattern || row.reversal_bias);
  return (
    <PanelFrame id="patterns">
      <PanelHeader
        title="Grafik Desenleri"
        subtitle="chart pattern + reversal evidence / backend passthrough"
      />
      {isLoading ? (
        <LoadingState />
      ) : !rows.length ? (
        <EmptyState message="Pattern verisi yok." />
      ) : (
        <div className="space-y-2">
          {!hasEvidence ? (
            <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-xs leading-5 text-white/52">
              Aktif desen veya reversal kaniti yok. Bu panel sadece backend Agent Matrix
              alanlarini okur; frontend teknik hesap yapmaz.
            </div>
          ) : null}
          {rows.map((row) => (
            <div key={row.symbol} className="rounded-lg border border-white/10 bg-black/24 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-sm text-white/90">{row.symbol}</div>
                  <div className="mt-0.5 text-[10px] uppercase tracking-widest text-white/36">
                    {row.decision.action}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-xs font-semibold ${patternTone(row.pattern)}`}>
                    {row.pattern ? PATTERN_LABEL[row.pattern] ?? row.pattern : "Desen yok"}
                  </div>
                  <div className={`mt-0.5 text-[10px] uppercase tracking-widest ${reversalTone(row.reversal_bias)}`}>
                    reversal {row.reversal_bias ?? "NEUTRAL"}
                  </div>
                </div>
              </div>
              {row.per_timeframe?.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {row.per_timeframe.map((cell) => (
                    <span
                      key={`${row.symbol}-${cell.timeframe}`}
                      className="rounded border border-white/10 bg-white/[0.035] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-white/55"
                      title={
                        cell.location_gate == null
                          ? `${cell.timeframe}: ${cell.bias}`
                          : `${cell.timeframe}: ${cell.bias} / location gate x${cell.location_gate.toFixed(2)}`
                      }
                    >
                      {cell.timeframe} {cell.bias}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </PanelFrame>
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
        <SpaceBrainScene brief={brief} active={activeLayer === 0} />
      </motion.div>
      <motion.div
        className="absolute inset-0"
        animate={{ opacity: activeLayer === 0 ? 0 : 0.78, scale: 0.98 + activeLayer * 0.04 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      >
        <QuantumBackplaneScene brief={brief} active={activeLayer > 0} />
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

function Layer1Stack({ items }: { items: Layer1StackItem[] }) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const stack = scroller?.querySelector<HTMLElement>(".layer1-stack");
    if (!scroller || !stack) return;

    const AUTO_ADVANCE_MS = 7000;
    const TRANSITION_MS = 1120;
    const MANUAL_LOCK_MS = TRANSITION_MS + 260;

    const readItems = () =>
      Array.from(stack.children)
        .filter((node): node is HTMLElement => node instanceof HTMLElement);

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let active = 0;
    let targets: number[] = [];
    let lockUntil = 0;
    let autoTimer = 0;
    let animationFrame = 0;
    let animationDoneTimer = 0;
    let resizeTimer = 0;
    let scrollSyncFrame = 0;
    let programmatic = false;

    const recalcTargets = () => {
      targets = readItems().map((panel) => Math.max(0, panel.offsetTop));
      return targets;
    };

    const applyState = (nextActive: number) => {
      const panels = readItems();
      if (!panels.length) return;

      panels.forEach((panel, index) => {
        const state =
          index < nextActive ? "covered" : index === nextActive ? "active" : "queued";
        panel.dataset.layer1State = state;
      });
      scroller.dataset.layer1Active = String(nextActive + 1);
      setActiveIndex(nextActive);
    };

    const finishSettling = () => {
      programmatic = false;
      scroller.dataset.layer1Settling = "false";
      applyState(active);
    };

    const animateScrollTo = (target: number, immediate = false) => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      if (animationDoneTimer) window.clearTimeout(animationDoneTimer);
      animationFrame = 0;
      animationDoneTimer = 0;
      const start = scroller.scrollTop;
      const distance = target - start;
      const duration = reducedMotion ? 0 : TRANSITION_MS;
      const startedAt = window.performance.now();

      programmatic = true;
      scroller.dataset.layer1Settling = "true";

      if (immediate || duration === 0 || Math.abs(distance) < 1) {
        scroller.scrollTop = target;
        finishSettling();
        return;
      }

      const ease = (t: number) => 1 - Math.pow(1 - t, 3);
      const step = (now: number) => {
        const progress = Math.min(1, (now - startedAt) / duration);
        scroller.scrollTop = start + distance * ease(progress);
        if (progress < 1) {
          animationFrame = window.requestAnimationFrame(step);
          return;
        }
        animationFrame = 0;
        scroller.scrollTop = target;
        animationDoneTimer = window.setTimeout(() => {
          animationDoneTimer = 0;
          finishSettling();
        }, 120);
      };
      animationFrame = window.requestAnimationFrame(step);
    };

    const moveTo = (nextIndex: number, mode: "auto" | "manual" | "sync") => {
      const currentTargets = recalcTargets();
      if (!currentTargets.length) return;
      const bounded =
        mode === "auto"
          ? ((nextIndex % currentTargets.length) + currentTargets.length) % currentTargets.length
          : Math.min(currentTargets.length - 1, Math.max(0, nextIndex));

      active = bounded;
      applyState(bounded);
      animateScrollTo(currentTargets[bounded], mode === "sync");
    };

    const scheduleAuto = () => {
      if (autoTimer) window.clearTimeout(autoTimer);
      autoTimer = window.setTimeout(() => {
        if (document.hidden) {
          scheduleAuto();
          return;
        }
        moveTo(active + 1, "auto");
        scheduleAuto();
      }, AUTO_ADVANCE_MS);
    };

    const syncFromScroll = () => {
      if (programmatic) return;
      if (!targets.length) recalcTargets();
      if (!targets.length) return;
      const current = scroller.scrollTop;
      let nearest = 0;
      targets.forEach((target, index) => {
        if (Math.abs(current - target) < Math.abs(current - targets[nearest])) {
          nearest = index;
        }
      });
      active = nearest;
      applyState(nearest);
    };

    const onWheel = (event: WheelEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (Math.abs(event.deltaY) < 8) return;

      event.preventDefault();
      const now = Date.now();
      if (now < lockUntil) return;
      lockUntil = now + MANUAL_LOCK_MS;
      moveTo(active + (event.deltaY > 0 ? 1 : -1), "manual");
      scheduleAuto();
    };

    const onScroll = () => {
      if (scrollSyncFrame) return;
      scrollSyncFrame = window.requestAnimationFrame(() => {
        scrollSyncFrame = 0;
        syncFromScroll();
      });
    };

    const scheduleLayoutSync = () => {
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        resizeTimer = 0;
        recalcTargets();
        if (!programmatic) moveTo(active, "sync");
      }, 180);
    };

    const onResize = () => {
      scheduleLayoutSync();
    };

    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            scheduleLayoutSync();
          });

    observer?.observe(scroller);
    readItems().forEach((panel) => observer?.observe(panel));
    scroller.addEventListener("wheel", onWheel, { passive: false });
    scroller.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);

    moveTo(0, "sync");
    scheduleAuto();

    return () => {
      if (autoTimer) window.clearTimeout(autoTimer);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      if (animationDoneTimer) window.clearTimeout(animationDoneTimer);
      if (resizeTimer) window.clearTimeout(resizeTimer);
      if (scrollSyncFrame) window.cancelAnimationFrame(scrollSyncFrame);
      observer?.disconnect();
      scroller.removeEventListener("wheel", onWheel);
      scroller.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, [items.length]);

  return (
    <div
      ref={scrollerRef}
      className="layer1-stack-scroll h-full overflow-y-auto p-4 md:p-5"
      aria-live="polite"
      aria-label={`Katman 1 panel ${activeIndex + 1} / ${items.length}`}
    >
      <div className="layer1-stack">
        {items.map((item) => (
          <div
            key={item.key}
            className="layer1-stack-item"
            data-layer1-key={item.key}
            data-layer1-state="queued"
          >
            {item.node}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CockpitView() {
  const { data, isLoading } = useCockpitBrief();
  const { data: ticketList } = useTradeTickets();
  const { data: paperState } = usePaperTradingState();
  const [activeLayer, setActiveLayer] = useState<LayerIndex>(0);
  const [direction, setDirection] = useState(1);
  const [hashSynced, setHashSynced] = useState(false);

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
    setHashSynced(true);
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  useEffect(() => {
    if (!hashSynced) return;
    const nextHash = `#layer-${activeLayer}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
    }
  }, [activeLayer, hashSynced]);

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
    const layer1Items: Layer1StackItem[] = [
      { key: "asset_card", node: <HolographicSignalDeck brief={brief} /> },
      { key: "news", node: <NewsPanel defaultView="radar" /> },
      {
        key: "event_scenario",
        node: (
          <section className="quantum-panel-cluster grid grid-cols-1 gap-5 xl:grid-cols-2">
            <EventCalendarPanel />
            <ScenarioPanel />
          </section>
        ),
      },
      { key: "capital_rotation", node: <CapitalRotationPanel /> },
      { key: "check_list", node: <ExecutionReadinessPanel /> },
      { key: "order_ticket", node: <OrderTicketPanel /> },
    ];

    layerContent = (
        <Layer1Stack items={layer1Items} />
      );
  } else if (activeLayer === 2) {
    layerContent = (
        <div className="h-full overflow-y-auto p-4 md:p-5">
          <div className="space-y-6 pb-12">
            <LayerHeader
              meta={LAYERS[2]}
              detail="Katman 1'in kopyasi degil: backend'in sagladigi derin kanit ekranlari burada lab mantigiyla okunur. Siralama: asset drilldown, fibonacci, backtest, brief archive, universe."
            >
              <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
            </LayerHeader>

            <div className="layer2-command-strip grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HudMetric label="Lab" value="5" tone="text-accent-cyan" />
              <HudMetric
                label="Aday"
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
              title="Asset Drilldown Terminal"
              detail="Secilen varlik icin backend analysis/asset, timeframe teknikleri ve market-session karar kapisi tek terminalde okunur."
            >
              <Layer2AssetDrilldownPanel />
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="02"
              title="Fibonacci / Level Lab"
              detail="Backend technical/insight ciktilariyla 1D ve 4H fib seviyeleri, yakin bolgeler ve confluence skoru okunur."
            >
              <Layer2FibonacciLabPanel />
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="03"
              title="Backtest / Outcome Lab"
              detail="Replay store, son decision trace ve manuel tetiklenen deterministic backtest sonucunu ayni kanit ekraninda toplar."
            >
              <Layer2BacktestOutcomePanel />
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="04"
              title="System Brief Archive"
              detail="Agent briefing, bildirim akisi ve worker hafizasi tek arxiv gibi okunur; Katman 0 sohbetine kaynak olan ozet buradadir."
            >
              <Layer2SystemBriefArchivePanel />
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="05"
              title="Asset Universe Lab"
              detail="Trade, snapshot, liquidity ve macro evreni backend asset registry uzerinden rol ve turlerine gore ayrilir."
            >
              <Layer2AssetUniversePanel />
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
                <RiskGateAnchorPanel />
              </GridCell>
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

          <Layer2DetailGroup
            index="D"
            title="Dashboard-Only Agent Yuzeyleri"
            detail="Dashboard registry'de olup cockpit'e birebir tasinmamis agent_narrator ve chat panelleri burada dogrudan okunur."
          >
            <DashboardGrid>
              <GridCell span="full">
                <AgentNarratorPanel />
              </GridCell>
              <GridCell span="full">
                <ChatPanel />
              </GridCell>
            </DashboardGrid>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            id="haberler_catalyst"
            index="E"
            title="Haberler & Catalyst"
            detail="dashboard#haberler_catalyst karsiligi: haber akisi, catalyst etkisi, olay takvimi ve senaryo tek Katman 3 grubunda."
          >
            <DashboardGrid>
              <GridCell span="full">
                <NewsPanel defaultView="radar" />
              </GridCell>
              <GridCell span="2">
                <CatalystImpactPanel />
              </GridCell>
              <GridCell span="1">
                <EventCalendarPanel />
              </GridCell>
              <GridCell span="full">
                <ScenarioPanel />
              </GridCell>
            </DashboardGrid>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="F"
            title="Grafik Desenleri ve Eksik Anchorlar"
            detail="dashboard#patterns artik Katman 3'te Agent Matrix'in pattern/reversal kanitlarini read-only olarak gosterir."
          >
            <DashboardGrid>
              <GridCell span="full">
                <PatternsAnchorPanel />
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
