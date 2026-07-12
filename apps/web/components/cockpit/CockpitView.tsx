"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";

import { DataQualityBadge } from "@/components/shell/DataQualityBadge";
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
  DATA_MODE_TONE,
  selectAgentBrief,
} from "@/lib/selectors/cockpit";

import { CapitalRotationPanel } from "@/components/panels/CapitalRotationPanel";
import { EventCalendarPanel } from "@/components/panels/EventCalendarPanel";
import { ExecutionReadinessPanel } from "@/components/panels/ExecutionReadinessPanel";
import { OrderTicketPanel } from "@/components/panels/OrderTicketPanel";
import { NewsPanel } from "@/components/panels/NewsPanel";
import { ScenarioPanel } from "@/components/panels/ScenarioPanel";
import { GovernorPanel } from "@/components/panels/GovernorPanel";
import { TaskQueuePanel } from "@/components/panels/TaskQueuePanel";
import { LearningPanel } from "@/components/panels/LearningPanel";
import { OutcomeLedgerPanel } from "@/components/panels/OutcomeLedgerPanel";
import { LearningWorkerPanel } from "@/components/panels/LearningWorkerPanel";
import { CalibrationPanel } from "@/components/panels/CalibrationPanel";
import { CalibrationJumpsPanel } from "@/components/panels/CalibrationJumpsPanel";
import { MistakeMemoryPanel } from "@/components/panels/MistakeMemoryPanel";
import { HistoricalEdgePanel } from "@/components/panels/HistoricalEdgePanel";
import { ConflictGateLearningPanel } from "@/components/panels/ConflictGateLearningPanel";
import { WeightProposalPanel } from "@/components/panels/WeightProposalPanel";
import { WeightHistoryPanel } from "@/components/panels/WeightHistoryPanel";
import { TfWeightsPanel } from "@/components/panels/TfWeightsPanel";
import { TfTargetsPanel } from "@/components/panels/TfTargetsPanel";
import { MissedOpportunitiesPanel } from "@/components/panels/MissedOpportunitiesPanel";
import { BookAuditPanel } from "@/components/panels/BookAuditPanel";
import { DatasetHealthPanel } from "@/components/panels/DatasetHealthPanel";
import { EdgeReportPanel } from "@/components/panels/EdgeReportPanel";
import { SubsignalScorecardPanel } from "@/components/panels/SubsignalScorecardPanel";
import { TfScoringShadowPanel } from "@/components/panels/TfScoringShadowPanel";
import { TfScoringRacePanel } from "@/components/panels/TfScoringRacePanel";
import { EntryExitQualityPanel } from "@/components/panels/EntryExitQualityPanel";
import { ExitForensicsPanel } from "@/components/panels/ExitForensicsPanel";
import { MetaGatePanel } from "@/components/panels/MetaGatePanel";
import { NewsEventStudyPanel } from "@/components/panels/NewsEventStudyPanel";
import { CalibrationHealthPanel } from "@/components/panels/CalibrationHealthPanel";
import { CouncilPanel } from "@/components/panels/CouncilPanel";
import { ExitBacktestPanel } from "@/components/panels/ExitBacktestPanel";
import { ZeroTwoStrategyPanel } from "@/components/panels/ZeroTwoStrategyPanel";
import { ZoneProposerPanel } from "@/components/panels/ZoneProposerPanel";
import { DiscoveryPanel } from "@/components/panels/DiscoveryPanel";
import { BacktestChallengerPanel } from "@/components/panels/BacktestChallengerPanel";
import { ThresholdAutotunePanel } from "@/components/panels/ThresholdAutotunePanel";
import { ThresholdAbPanel } from "@/components/panels/ThresholdAbPanel";
import { GuardSafetyPanel } from "@/components/panels/GuardSafetyPanel";
import { AgentModePanel } from "@/components/panels/AgentModePanel";
import { LearningBrainPanel } from "@/components/panels/LearningBrainPanel";
import type { CockpitBrief } from "@/types/generated/api";

import { HolographicSignalDeck } from "./HolographicSignalDeck";
import { Layer0ReporterAgent, type Layer0HeroProps } from "./Layer0ReporterAgent";
import {
  Layer2AssetDrilldownPanel,
  Layer2AssetUniversePanel,
  Layer2BacktestOutcomePanel,
  Layer2ElliottZoneLabPanel,
  Layer2FibonacciLabPanel,
  Layer2SoulAssetStrip,
  Layer2SetupConflictLabPanel,
  Layer2SystemBriefArchivePanel,
  Layer2TechnicalChartPanel,
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
  label: string;
  node: ReactNode;
};

const LAYERS: LayerMeta[] = [
  {
    index: 0,
    code: "00",
    title: "Brain",
    shortTitle: "Brain",
    subtitle: "ilk acilis / kendi kendine tarama / iletisim",
    depth: "dis yuzey",
  },
  {
    index: 1,
    code: "01",
    title: "Heart",
    shortTitle: "Heart",
    subtitle: "6 ana karar yuzeyi / operasyon bakisi",
    depth: "operasyon odasi",
  },
  {
    index: 2,
    code: "02",
    title: "Soul",
    shortTitle: "Soul",
    subtitle: "kanit, risk, piyasa yapisi ve analiz gruplari",
    depth: "analiz cekirdegi",
  },
  {
    index: 3,
    code: "03",
    title: "Conscious",
    shortTitle: "Conscious",
    subtitle: "oz-yonetim · onay · egitim · sonuc defteri",
    depth: "bilinc / ogrenme odasi",
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

// Risk kapısı aksiyon kodu → Katman 0 kutusuna sığan kısa Türkçe durum.
// Ham kod ScanItem.code ile ayrıca taşınır (teknik referans satırı).
const RISK_ACTION_LABEL: Record<string, string> = {
  HOLD: "Yeni girişe açık",
  WATCH: "İzleme modunda",
  HEDGE_INCREASE: "Hedge artırımı önerili",
  NO_POSITION_INCREASE: "Yeni pozisyon açılmaz",
  RISK_REDUCE: "Risk azaltımı gerekli",
  KILL_SWITCH: "Acil fren aktif",
};

function formatLayer0WatchCondition(item: { key: string; label: string; detail?: string }) {
  if (item.key === "provider_restored") return null;

  const text = `${item.label} ${item.detail ?? ""}`.toLowerCase();
  if (item.key === "catalyst_halflife") {
    if (text.includes("geopolitical_escalation")) return "Jeopolitik risk normalleşsin";
    if (text.includes("geopolitical_deescalation")) return "Jeopolitik yumuşama netleşsin";
    if (text.includes("inflation_data")) return "Enflasyon verisi sindirilsin";
    if (text.includes("jobs_data")) return "İstihdam verisi sindirilsin";
    if (text.includes("central_bank")) return "Merkez bankası etkisi sindirilsin";
    if (text.includes("oil_supply") || text.includes("oil_inventory")) {
      return "Petrol arz etkisi sakinleşsin";
    }
    if (text.includes("crypto_etf_flow")) return "ETF akışı netleşsin";
    if (text.includes("funding_oi_squeeze")) return "Kaldıraç baskısı sönsün";
    if (text.includes("rumor_unverified")) return "Doğrulanmamış haber netleşsin";
    return "Catalyst etkisi sakinleşsin";
  }

  return item.label;
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
  badge = "read-only",
  badgeTone = "border-accent-cyan/20 bg-accent-cyan/8 text-accent-cyan/72",
  children,
}: {
  index: string;
  title: string;
  detail: string;
  id?: string;
  /** Sağ üst rozet metni. Varsayılan "read-only"; owner kontrolü olan
   *  gruplarda "owner kontrolü" / "owner onayı" gibi etiketle override edilir. */
  badge?: string;
  badgeTone?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="layer2-detail-group">
      <div className="layer2-detail-beam" />
      <div className="layer2-detail-scan" />
      <header className="layer2-detail-header relative z-10 mb-4 flex flex-col gap-3 border-b border-white/[0.08] pb-3 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="layer2-detail-title-row flex items-center gap-3">
            <span className="layer2-detail-index">{index}</span>
            <div className="h-px flex-1 bg-gradient-to-r from-accent-cyan/45 via-white/10 to-transparent" />
          </div>
          <h3 className="layer2-detail-title mt-3 font-display text-xl leading-none text-white/92 md:text-2xl">
            {title}
          </h3>
          <p className="layer2-detail-copy mt-2 max-w-4xl text-sm leading-6 text-white/52">{detail}</p>
        </div>
        <span className={`layer2-detail-badge shrink-0 rounded-full border px-3 py-1 text-[10px] uppercase tracking-widest ${badgeTone}`}>
          {badge}
        </span>
      </header>
      <div className="layer2-detail-body relative z-10">{children}</div>
    </section>
  );
}

/** Öğrenme Hattı adım sarmalayıcısı — panelin üstüne akış sırası + tek satır
 *  günlük-dil açıklama koyar. Panel içeriğine dokunmaz. */
function Layer2CompositeBlock({
  label,
  detail,
  wide = false,
  children,
}: {
  label: string;
  detail: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`layer2-composite-block ${wide ? "layer2-composite-block--wide" : ""}`}>
      <header className="layer2-composite-block__head">
        <span>{label}</span>
        <p>{detail}</p>
      </header>
      <div className="layer2-composite-block__body">{children}</div>
    </section>
  );
}

function LearnStep({
  step,
  label,
  wide = false,
  children,
}: {
  step: string;
  label: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={wide ? "lg:col-span-2" : undefined}>
      <div className="mb-1.5 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-white/40">
        <span className="shrink-0 rounded border border-accent-cyan/25 bg-accent-cyan/10 px-1.5 py-0.5 font-mono font-bold text-accent-cyan/85">
          ADIM {step}
        </span>
        <span className="min-w-0 truncate">{label}</span>
      </div>
      {children}
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
    <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-white/10 bg-black/40 p-1.5 shadow-[0_18px_48px_rgba(0,0,0,0.3)] backdrop-blur-xl">
      <button
        type="button"
        disabled={previous == null}
        onClick={() => previous != null && onSelect(previous)}
        className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-white/62 transition-colors hover:border-white/24 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
      >
        Geri
      </button>
      <div className="flex items-center gap-1">
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
            aria-label={`Katman ${layer.index} ${layer.title}`}
          />
        ))}
      </div>
      <button
        type="button"
        disabled={next == null}
        onClick={() => next != null && onSelect(next)}
        className="rounded-full border border-accent-cyan/35 bg-accent-cyan/8 px-3 py-1.5 text-xs text-accent-cyan transition-colors hover:bg-accent-cyan/14 disabled:cursor-not-allowed disabled:opacity-30"
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
  const [mobileStage, setMobileStage] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(max-width: 768px)");
    const sync = () => setMobileStage(query.matches);
    sync();
    if (query.addEventListener) {
      query.addEventListener("change", sync);
      return () => query.removeEventListener("change", sync);
    }
    query.addListener(sync);
    return () => query.removeListener(sync);
  }, []);

  return (
    <div
      className="relative z-10 mx-auto h-full min-h-0 w-full min-w-0 max-w-7xl overflow-hidden px-2 py-2 sm:px-4 sm:py-3 md:px-6 md:py-4 xl:pl-24"
      style={{ perspective: 1800 }}
    >
      <motion.section
        key={activeLayer}
        initial={{
          opacity: 0,
          scale: mobileStage ? 1 : direction >= 0 ? 1.16 : 0.84,
          z: mobileStage ? 0 : direction >= 0 ? -360 : 260,
          rotateX: mobileStage ? 0 : direction >= 0 ? 7 : -5,
          filter: mobileStage ? "blur(0px)" : "blur(18px)",
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

  const scrollToItem = (key: string) => {
    const scroller = scrollerRef.current;
    const panel = scroller?.querySelector<HTMLElement>(`[data-layer1-key="${key}"]`);
    if (!scroller || !panel) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    scroller.scrollTo({
      top: panel.offsetTop,
      behavior: reducedMotion ? "auto" : "smooth",
    });
  };

  useEffect(() => {
    const scroller = scrollerRef.current;
    const stack = scroller?.querySelector<HTMLElement>(".layer1-stack");
    if (!scroller || !stack) return;

    const MANUAL_LOCK_MS = 1400;
    const TRANSITION_MS = 1150;

    const readItems = () =>
      Array.from(stack.children).filter(
        (node): node is HTMLElement => node instanceof HTMLElement,
      );

    const readGap = () => {
      const value = Number.parseFloat(window.getComputedStyle(stack).gap);
      return Number.isFinite(value) ? value : 0;
    };

    const readTargets = () => {
      const panels = readItems();
      const gap = readGap();
      let cursor = 0;
      return panels.map((panel) => {
        const target = cursor;
        cursor += panel.offsetHeight + gap;
        return target;
      });
    };

    const isMobileStack = window.matchMedia("(max-width: 768px)").matches;
    if (isMobileStack) {
      let ticking = false;

      const syncMobileState = () => {
        const panels = readItems();
        if (!panels.length) return;

        const current = scroller.scrollTop;
        let nearest = 0;
        panels.forEach((panel, index) => {
          panel.dataset.layer1State = "active";
          if (Math.abs(current - panel.offsetTop) < Math.abs(current - panels[nearest].offsetTop)) {
            nearest = index;
          }
        });
        scroller.dataset.layer1Active = String(nearest + 1);
        setActiveIndex(nearest);
      };

      const onMobileScroll = () => {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(() => {
          ticking = false;
          syncMobileState();
        });
      };

      syncMobileState();
      scroller.addEventListener("scroll", onMobileScroll, { passive: true });
      window.addEventListener("resize", syncMobileState);
      return () => {
        scroller.removeEventListener("scroll", onMobileScroll);
        window.removeEventListener("resize", syncMobileState);
      };
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let active = 0;
    let lockUntil = 0;
    let animationFrame = 0;
    let animationDoneTimer = 0;
    let resizeTimer = 0;
    let scrollSettleTimer = 0;
    let programmatic = false;

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
        animationDoneTimer = window.setTimeout(() => {
          animationDoneTimer = 0;
          finishSettling();
        }, 120);
      };
      animationFrame = window.requestAnimationFrame(step);
    };

    const moveTo = (nextIndex: number, mode: "manual" | "sync") => {
      const targets = readTargets();
      if (!targets.length) return;
      const bounded = Math.min(targets.length - 1, Math.max(0, nextIndex));

      active = bounded;
      applyState(bounded);
      animateScrollTo(targets[bounded], mode === "sync");
    };

    const syncFromScroll = () => {
      if (programmatic) return active;
      const targets = readTargets();
      if (!targets.length) return active;

      const current = scroller.scrollTop;
      let nearest = 0;
      targets.forEach((target, index) => {
        if (Math.abs(current - target) < Math.abs(current - targets[nearest])) {
          nearest = index;
        }
      });
      active = nearest;
      applyState(nearest);
      return nearest;
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
    };

    const onScroll = () => {
      window.requestAnimationFrame(syncFromScroll);
      if (programmatic) return;
      if (scrollSettleTimer) window.clearTimeout(scrollSettleTimer);
      scrollSettleTimer = window.setTimeout(() => {
        scrollSettleTimer = 0;
        if (!programmatic) {
          const nearest = syncFromScroll();
          moveTo(nearest, "manual");
        }
      }, 180);
    };

    const scheduleLayoutSync = () => {
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        resizeTimer = 0;
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

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      if (animationDoneTimer) window.clearTimeout(animationDoneTimer);
      if (resizeTimer) window.clearTimeout(resizeTimer);
      if (scrollSettleTimer) window.clearTimeout(scrollSettleTimer);
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
      <div className="layer1-mobile-panel-tabs md:hidden" aria-label="Heart panelleri">
        {items.map((item, index) => (
          <button
            key={item.key}
            type="button"
            onClick={() => scrollToItem(item.key)}
            className={index === activeIndex ? "is-active" : ""}
            aria-current={index === activeIndex ? "true" : undefined}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            {item.label}
          </button>
        ))}
      </div>
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
  const [selectedLayer2Symbol, setSelectedLayer2Symbol] = useState("BTCUSD");

  const activateLayer = (next: LayerIndex) => {
    setDirection(next >= activeLayer ? 1 : -1);
    setActiveLayer(next);
  };

  // Katmanlar arası yatay kaydırma geçişi (dokunmatik). Sağdan-sola → bir sonraki
  // (derinleş), soldan-sağa → bir önceki katman. Yalnız BASKIN yatay hareket sayılır
  // (dikey kaydırma/scroll'u bozmaz); input, sohbet kutusu ve yatay-kaydırmalı panel
  // sekmeleri muaf (data-no-swipe / closest guard).
  const swipeRef = useRef<{ x: number; y: number; t: number } | null>(null);
  const onTouchStart = (event: React.TouchEvent) => {
    if (event.touches.length !== 1) {
      swipeRef.current = null;
      return;
    }
    const t = event.touches[0];
    swipeRef.current = { x: t.clientX, y: t.clientY, t: Date.now() };
  };
  const onTouchEnd = (event: React.TouchEvent) => {
    const start = swipeRef.current;
    swipeRef.current = null;
    if (!start) return;
    const target = event.target as HTMLElement | null;
    if (
      target?.closest(
        'input, textarea, [contenteditable="true"], .layer1-mobile-panel-tabs, .layer0-voice-input, [data-no-swipe]',
      )
    ) {
      return;
    }
    const t = event.changedTouches[0];
    if (!t) return;
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    const dt = Date.now() - start.t;
    // Baskın yatay + yeterli mesafe + hızlı jest değilse yok say.
    if (dt > 700 || Math.abs(dx) < 64 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
    if (dx < 0) {
      const next = Math.min(3, activeLayer + 1) as LayerIndex;
      if (next !== activeLayer) activateLayer(next);
    } else {
      const prev = Math.max(0, activeLayer - 1) as LayerIndex;
      if (prev !== activeLayer) activateLayer(prev);
    }
  };

  useEffect(() => {
    let initialHashRead = true;
    const applyHash = () => {
      const isInitialHashRead = initialHashRead;
      initialHashRead = false;
      const mobileStart =
        window.matchMedia("(max-width: 768px)").matches && isInitialHashRead;
      if (mobileStart && parseLayerHash(window.location.hash) !== 0) {
        setActiveLayer(0);
        setDirection(1);
        window.history.replaceState(null, "", "#layer-0");
        return;
      }
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
  const watch = (brief.next_watch_conditions ?? [])
    .map((item) => {
      const label = formatLayer0WatchCondition(item);
      return label ? { key: item.key, label } : null;
    })
    .filter((item): item is { key: string; label: string } => Boolean(item))
    .slice(0, 3);
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
  // P&L başlığa hero.pnl üzerinden eklenir — detail satırında TEKRAR edilmez.
  const decisionTitle = hasOpenPositions
    ? `${openPaperPositions} açık işlem`
    : activeTicket
      ? `${activeTicket.symbol} ${activeTicket.side.toUpperCase()}`
      : "Şu an işlem yok";
  const decisionDetail = hasOpenPositions
    ? newSignalNote ?? "Yeni sinyal yok — motor adayları izliyor."
    : activeTicket
      ? `${activeTicket.timeframe} · ${activeTicket.display.confidence_text}`
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
  // Aynı sembol birden çok TF'te aday olabilir — listede tekilleştir.
  const topSymbols = candidates.length
    ? [...new Set(candidates.map((candidate) => candidate.symbol ?? "?"))]
        .slice(0, 4)
        .join(" / ")
    : "radar boş";

  const currentMeta = LAYERS[activeLayer];
  let layerContent: ReactNode;
  const dqsTone =
    (dqs ?? 0) >= 80 ? "text-signal-up" : (dqs ?? 0) >= 60 ? "text-amber-300" : "text-signal-down";
  const riskScanState =
    riskAction === "HOLD"
      ? "OK"
      : riskAction === "NO_POSITION_INCREASE"
        ? "IZLE"
        : riskAction === "KILL_SWITCH" ||
            riskAction === "RISK_REDUCE" ||
            riskAction === "BLOCKED"
          ? "ENGEL"
          : riskClear
            ? "OK"
            : "IZLE";
  const heroProps: Layer0HeroProps = {
    title: decisionTitle,
    detail: decisionDetail,
    tone: decisionTone,
    dqs: { value: formatScore(dqs), tone: dqsTone },
    pnl: {
      value: hasOpenPositions
        ? `${unrealizedPnl >= 0 ? "+" : ""}$${Math.round(unrealizedPnl).toLocaleString()}`
        : activeTicket
          ? `R:R ${ticketRr != null ? ticketRr.toFixed(2) : "--"}`
          : "flat",
      tone: hasOpenPositions
        ? unrealizedPnl >= 0
          ? "text-emerald-200"
          : "text-red-200"
        : activeTicket
          ? "text-emerald-200"
          : "text-slate-300",
    },
    topSymbols,
    scans: {
      veri: {
        label: "Veri omurgası",
        value: `${brief.data_mode} · ${dataTrusted ? "güvenilir" : "düşük güven"}`,
        ok: dataTrusted,
        state: dataTrusted ? "OK" : "ENGEL",
      },
      risk: {
        label: "Risk kapısı",
        value: RISK_ACTION_LABEL[riskAction] ?? riskAction,
        code: riskAction,
        ok: riskClear,
        state: riskScanState,
        href: "/dashboard#risk_gate",
      },
      sinyal: {
        label: "Sinyal adayları",
        value: `${actionableCount}/${candidates.length} işleme hazır`,
        ok: actionableCount > 0,
        state: actionableCount > 0 ? "OK" : "IZLE",
      },
    },
    watch,
  };

  if (activeLayer === 0) {
    layerContent = (
      <div className="h-full snap-y snap-mandatory overflow-y-auto scroll-smooth p-2 sm:p-3 md:p-4 xl:snap-none xl:overflow-hidden">
        <Layer0ReporterAgent hero={heroProps} onNavigate={activateLayer} />
      </div>
      );
  } else if (activeLayer === 1) {
    const layer1Items: Layer1StackItem[] = [
      { key: "holographic_signals", label: "Sinyal Kartlari", node: <HolographicSignalDeck brief={brief} /> },
      { key: "news", label: "Haberler", node: <NewsPanel defaultView="radar" /> },
      { key: "execution_readiness", label: "Checklist", node: <ExecutionReadinessPanel /> },
      { key: "event_calendar", label: "Olay Takvimi", node: <EventCalendarPanel /> },
      { key: "scenario", label: "Senaryo", node: <ScenarioPanel /> },
      { key: "capital_rotation", label: "Likidite", node: <CapitalRotationPanel /> },
      { key: "order_ticket", label: "Order Ticket", node: <OrderTicketPanel /> },
    ];

    layerContent = (
        <Layer1Stack items={layer1Items} />
      );
  } else if (activeLayer === 2) {
    layerContent = (
        <div className="h-full overflow-y-auto p-4 md:p-5">
          <div className="layer2-soul-stage space-y-6 pb-12">
            <LayerHeader
              meta={LAYERS[2]}
              detail="Soul, secili assetin ruhunu okur: Katman 1 asset kartlarindan secilen varlik icin teknik, seviye, dalga, likidite ve trace kanitlari tek akista incelenir."
            >
              <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
            </LayerHeader>

            <Layer2SoulAssetStrip
              brief={brief}
              selectedSymbol={selectedLayer2Symbol}
              onSelectSymbol={setSelectedLayer2Symbol}
            />

            <div className="layer2-command-strip grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HudMetric label="Asset" value={selectedLayer2Symbol} tone="text-accent-cyan" />
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
              title={`${selectedLayer2Symbol} Asset Command`}
              detail="Secili assetin terminal okumasi, seans kapisi, registry rolleri ve evren kaydi tek yerde."
            >
              <div className="layer2-composite-flow">
                <Layer2CompositeBlock
                  label="Core terminal"
                  detail="Teknik skor, timeframe matrisi ve market-session kapisi"
                  wide
                >
                  <Layer2AssetDrilldownPanel selectedSymbol={selectedLayer2Symbol} />
                </Layer2CompositeBlock>
                <Layer2CompositeBlock
                  label="Universe record"
                  detail="Registry rolleri, bucket kaydi, snapshot fiyati ve DQS"
                  wide
                >
                  <Layer2AssetUniversePanel selectedSymbol={selectedLayer2Symbol} />
                </Layer2CompositeBlock>
              </div>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="02"
              title={`${selectedLayer2Symbol} Structure & Liquidity`}
              detail="Chart, seviyeler, dalga/zone kaniti ve volume-liquidity motorlari ayni piyasa-yapisi panelinde."
            >
              <div className="layer2-composite-flow">
                <Layer2CompositeBlock
                  label="Multi-timeframe chart"
                  detail="Raw OHLCV, timeframe secimi, son bar tablosu ve teknik snapshot"
                  wide
                >
                  <Layer2TechnicalChartPanel selectedSymbol={selectedLayer2Symbol} />
                </Layer2CompositeBlock>
                <div className="layer2-composite-grid layer2-composite-grid--market">

                  <Layer2CompositeBlock
                    label="Fibonacci / levels"
                    detail="1D ve 4H fib seviyeleri, yakin bolgeler ve confluence"
                  >
              <Layer2FibonacciLabPanel selectedSymbol={selectedLayer2Symbol} />
                  </Layer2CompositeBlock>

                  <Layer2CompositeBlock
                    label="Elliott / zones"
                    detail="EVIDENCE-only wave senaryosu ve support/resistance zone analizi"
                  >
              <Layer2ElliottZoneLabPanel selectedSymbol={selectedLayer2Symbol} />
                  </Layer2CompositeBlock>

                  <Layer2CompositeBlock
                    label="Volume / VWAP / liquidity"
                    detail="Validation, anchored VWAP, sweep, exhaustion, location ve trigger"
                    wide
                  >
              <Layer2SetupConflictLabPanel selectedSymbol={selectedLayer2Symbol} />
                  </Layer2CompositeBlock>
                </div>
              </div>
            </Layer2DetailGroup>

            <Layer2DetailGroup
              index="03"
              title={`${selectedLayer2Symbol} Evidence Memory`}
              detail="Replay, outcome, decision trace, agent brief ve bildirim arsivi secili assete filtrelenmis tek hafiza panelinde."
            >
              <div className="layer2-composite-flow">
                <Layer2CompositeBlock
                  label="Trace / outcome"
                  detail="Replay store, backtest metrikleri ve son karar izleri"
                  wide
                >
                  <Layer2BacktestOutcomePanel selectedSymbol={selectedLayer2Symbol} />
                </Layer2CompositeBlock>

                <Layer2CompositeBlock
                  label="Brief archive"
                  detail="Agent briefing, bildirim akisi ve worker memory"
                  wide
                >
                  <Layer2SystemBriefArchivePanel selectedSymbol={selectedLayer2Symbol} />
                </Layer2CompositeBlock>
              </div>
            </Layer2DetailGroup>

          </div>
        </div>
      );
  } else {
    layerContent = (
      <div className="h-full overflow-y-auto p-4 md:p-5">
        <div className="space-y-6 pb-12">
          <LayerHeader
            meta={LAYERS[3]}
            detail="Katman 3, sistemin gecmisten ne ogrendigini, hangi ayarlari onerdigini ve hangi hatalari takip ettigini bolum bolum gosterir."
          >
            <DataQualityBadge dqs={dqs} generatedAt={data?.generated_at} />
          </LayerHeader>

          <Layer2DetailGroup
            index="01"
            title="Ne Ogrendim — Kitap Denetimi"
            detail="Acik islemlerdeki mantik hatalarini kapanis beklemeden gosterir: ayni varlikta zit yon, tek varlikta asiri yogunlasma, ayni sinyalin TF'lere kopyalanmasi, tek-yon kitap."
            badge="canli ogrenme"
            badgeTone="border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan"
          >
            <BookAuditPanel />
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="02"
            title="Sistem Yonetimi"
            detail="Owner kontrolu modlar: governor ozeti, agent modu ve gorev kuyrugu."
            badge="owner kontrolu"
            badgeTone="border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          >
            <div className="grid gap-3 lg:grid-cols-2">
              <div className="lg:col-span-2"><GovernorPanel /></div>
              <div className="lg:col-span-2"><AgentModePanel /></div>
              <div className="lg:col-span-2"><TaskQueuePanel /></div>
            </div>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="03"
            title="Ogrenme Hatti"
            detail="Paneller ogrenme akisinin sirasinda dizildi: once ham veri toplanir ve dogrulanir, veri yeterliyse motor ogrenir, kazanc tutarliligi kapisi acilirsa otomatik ince-ayar devreye girer. Her adim read-only rapordur; config'e yazan adimlar rollback aglidir."
            badge="read-only"
          >
            <div className="grid gap-3 lg:grid-cols-2">
              <LearnStep step="01" label="Ham veri — kapanan her işlem deftere yazılır" wide>
                <OutcomeLedgerPanel />
              </LearnStep>
              <LearnStep step="02" label="Veri yeterli ve temiz mi">
                <DatasetHealthPanel />
              </LearnStep>
              <LearnStep step="03" label="Öğrenme motoru — 5 dk'da bir koşar">
                <LearningWorkerPanel />
              </LearnStep>
              <LearnStep step="04" label="Ne öğrendi — kalibrasyon + ağırlıklar">
                <LearningPanel />
              </LearnStep>
              <LearnStep step="05" label="Güvenlik kapısı — kazanç kalıcı mı, şans mı">
                <EdgeReportPanel />
              </LearnStep>
              <LearnStep step="06" label="Teşhis — kayıp nereden sızıyor">
                <EntryExitQualityPanel />
              </LearnStep>
              <LearnStep step="07" label="Çıkış otopsisi — en pahalı çıkış hataları">
                <ExitForensicsPanel />
              </LearnStep>
              <LearnStep step="08" label="Otomatik ince-ayar — kapı açıksa, rollback'li">
                <ThresholdAutotunePanel />
              </LearnStep>
              <LearnStep step="09" label="Koruma filtreleri — zarar verirse oto-kapanır">
                <GuardSafetyPanel />
              </LearnStep>
              <LearnStep step="10" label="Elle deney — A/B backtest, canlıya dokunmaz">
                <ThresholdAbPanel />
              </LearnStep>
              <LearnStep step="11" label="Keşif — yeni aday tarama (hipotetik, işlem açmaz)">
                <DiscoveryPanel />
              </LearnStep>
              <LearnStep step="12" label="Backtest challenger — geçmiş-prova kanıtı (izole, canlıya dokunmaz)">
                <BacktestChallengerPanel />
              </LearnStep>
              <LearnStep step="13" label="Öğrenme Beyni — tüm kanıt tek ekranda (özet)" wide>
                <LearningBrainPanel />
              </LearnStep>
              <LearnStep step="14" label="Sinyal karnesi — hangi sinyal hangi zaman diliminde kanıtlı" wide>
                <SubsignalScorecardPanel />
              </LearnStep>
              <LearnStep step="15" label="Yeni beyin (gölge) — rejim-anahtarlı v2 yönü, izler karar vermez" wide>
                <TfScoringShadowPanel />
              </LearnStep>
              <LearnStep step="16" label="Yarış raporu — yeni beyin eskiyi/tabanı geçiyor mu, terfi owner onayıyla" wide>
                <TfScoringRacePanel />
              </LearnStep>
              <LearnStep step="17" label="Meta-kapı (gölge) — GİR/GİRME ikinci görüşü, seçiciliği ölçer karar vermez" wide>
                <MetaGatePanel />
              </LearnStep>
              <LearnStep step="18" label="Haberin edge'i (gölge) — haber sonrası fiyat yönü tutuyor mu, ölçer karar vermez" wide>
                <NewsEventStudyPanel />
              </LearnStep>
              <LearnStep step="19" label="Kalibrasyon sağlığı — güven-ayarı oturmuşluğu + gerçekleşen-R kâr hesabı hazırlığı (tek eksen, birleşik panel)" wide>
                <CalibrationHealthPanel />
              </LearnStep>
              <LearnStep step="20" label="Çıkış verim backtest — en verimli sabit + trailing stop aralığı (gerçek fiyat geçmişi)" wide>
                <ExitBacktestPanel />
              </LearnStep>
              <LearnStep step="21" label="0-2 strateji + house-money — owner nihai LONG akışının gölge karnesi (giriş + fib hedef + trailing + sabit-bahis re-giriş)" wide>
                <ZeroTwoStrategyPanel />
              </LearnStep>
              <LearnStep step="22" label="Bölge önerileri — owner kesişim yöntemi her asset'te: işaretli grafik + iptal edilmedikçe onaylı (onaylılar flag açıkken SL/TP yerleşimini etkiler)" wide>
                <ZoneProposerPanel />
              </LearnStep>
              <LearnStep step="23" label="Konsey karnesi — katmanlar birlikte ne söylüyor: modül yayılımları + veriden türetilen sanki-filtreler (in-sample kanıt)" wide>
                <CouncilPanel />
              </LearnStep>
            </div>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="04"
            title="Kalibrasyon ve Agirliklar"
            detail="Guven kalibrasyonu, TF agirliklari, SL/TP hedef ogrenmesi ve owner onayina sunulan agirlik degisimleri."
            badge="owner onayi"
            badgeTone="border-amber-400/30 bg-amber-400/10 text-amber-200"
          >
            <div className="grid gap-3 lg:grid-cols-2">
              <CalibrationPanel />
              <CalibrationJumpsPanel />
              <TfWeightsPanel />
              <div className="lg:col-span-2"><TfTargetsPanel /></div>
              <WeightProposalPanel />
              <WeightHistoryPanel />
            </div>
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="05"
            title="Hata Hafizasi"
            detail="Tekrar eden hata parmak izleri ve benzer gecmis setup performansi — sistem hangi kosullarda zayif kalmis."
            badge="read-only"
          >
            <div className="grid gap-3 lg:grid-cols-2">
              <MistakeMemoryPanel />
              <HistoricalEdgePanel />
            </div>
          </Layer2DetailGroup>

          <div className="relative mt-2 flex items-center gap-3 pt-2">
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-fuchsia-400/35 to-transparent" />
            <span className="rounded-full border border-fuchsia-400/25 bg-fuchsia-400/8 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-fuchsia-200/80">
              Shadow · Gozlem Seridi
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-fuchsia-400/35 to-transparent" />
          </div>
          <p className="-mt-3 px-1 text-[11px] leading-5 text-white/45">
            Bu bolumdeki katmanlar <strong className="text-white/65">karari henuz yonetmez</strong> — yalniz olculur
            (shadow-first). Yeterince dogrulaninca owner kararyla canliya alinir.
          </p>

          <Layer2DetailGroup
            index="S1"
            title="Kacan Firsatlar"
            detail="Acilmayan valid setup'larin sonucu: kacan kazanc, onlenen zarar ve sure dolan adaylar (gozlem)."
            badge="shadow"
            badgeTone="border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-200"
          >
            <MissedOpportunitiesPanel />
          </Layer2DetailGroup>

          <Layer2DetailGroup
            index="S2"
            title="Conflict Gate Ogrenmesi"
            detail="Conflict gate profil modlari ve gecmis route dogrulama performansi — gate aktivasyon kararina veri (gozlem)."
            badge="shadow"
            badgeTone="border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-200"
          >
            <ConflictGateLearningPanel />
          </Layer2DetailGroup>
        </div>
      </div>
    );
  }

  return (
    <main
      className="cockpit-root relative grid min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#02030a] text-white"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <LayerDepthBackdrop activeLayer={activeLayer} brief={brief} />

      <header className="pointer-events-none relative z-30 min-w-0 overflow-hidden border-b border-white/[0.08] bg-black/24 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-3 py-1.5 sm:gap-3 sm:px-4 sm:py-2.5 md:px-6 xl:pl-24">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-xl border border-accent-cyan/35 bg-accent-cyan/10 font-display text-xs text-accent-cyan shadow-[0_0_28px_rgba(34,211,238,0.16)] sm:h-10 sm:w-10 sm:text-sm">
              EY
            </div>
            <div className="min-w-0">
              <div className="truncate font-display text-xs leading-tight text-white/92 sm:text-sm">
                E-yAy Brain
              </div>
              <div className="hidden text-[10px] uppercase tracking-[0.22em] text-white/42 sm:block">
                Human-AI Interface
              </div>
            </div>
          </div>
          {activeLayer !== 0 ? (
          <div className="hidden min-w-0 flex-1 justify-center md:flex">
            <div className="truncate rounded-full border border-white/10 bg-white/[0.035] px-4 py-1.5 text-[10px] uppercase tracking-[0.2em] text-white/55">
              {currentMeta.subtitle}
            </div>
          </div>
          ) : (
            <div className="hidden min-w-0 flex-1 md:block" />
          )}
          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
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
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/20 bg-amber-400/8 px-1.5 py-1 text-[8px] uppercase tracking-normal text-amber-300 sm:gap-1.5 sm:px-2.5 sm:text-[10px] sm:tracking-widest">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shadow-[0_0_10px_currentColor]" />
              <span className="sm:hidden">NX</span>
              <span className="hidden sm:inline">No_Execution</span>
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
              className="pointer-events-auto grid h-8 w-8 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.04] text-white/60 transition-colors hover:border-accent-cyan/35 hover:text-accent-cyan sm:h-9 sm:w-9"
            >
              <span className="text-base leading-none">⚙</span>
            </button>
          </div>
        </div>
      </header>

      <LayerRail activeLayer={activeLayer} onSelect={activateLayer} />

      <LayerStage activeLayer={activeLayer} direction={direction}>
        {layerContent}
      </LayerStage>

      <footer className="pointer-events-none relative z-30 min-w-0 overflow-hidden border-t border-white/[0.08] bg-black/30 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-center gap-x-6 gap-y-1 px-3 pb-[calc(0.375rem+env(safe-area-inset-bottom))] pt-1.5 md:justify-between md:px-6 md:py-2 xl:pl-24">
          <LayerControls activeLayer={activeLayer} onSelect={activateLayer} />
          <div className="hidden flex-wrap items-center justify-end gap-x-6 gap-y-1 md:flex">
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
      </footer>
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
