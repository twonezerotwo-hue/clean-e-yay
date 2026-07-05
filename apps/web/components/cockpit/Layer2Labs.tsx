"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type {
  AssetAnalysisTimeframe,
  AssetRegistryItem,
  ChartBar,
  ChartTimeframe,
  ElliottAnalysis,
  ExhaustionAnalysis,
  FibonacciFrame,
  FibonacciLevel,
  LiquiditySweepAnalysis,
  LocationScoreAnalysis,
  PriceZone,
  TriggerAnalysis,
  VolumeAnalysis,
  VWAPAnalysis,
  ZoneAnalysis,
} from "@/lib/api/client";
import {
  useAgentBriefing,
  useAssetAnalysis,
  useAssetRegistry,
  useConflictGateStatus,
  useConflictGateValidation,
  useDataSnapshot,
  useDecisionMatrix,
  useElliottScenario,
  useExhaustionScore,
  useLiquiditySweepAnalysis,
  useLocationScore,
  useMarketSessionAsset,
  useNotifications,
  useReplayBacktest,
  useReplayDecisionTrace,
  useReplayStatus,
  useRegimeReport,
  useShadowComparison,
  useSystemHealth,
  useTechnicalChart,
  useTechnicalInsight,
  useTriggerAnalysis,
  useVolumeAnalysis,
  useVwapAnalysis,
  useZoneAnalysis,
} from "@/lib/queries/hooks";
import type {
  AgentBrief,
  AgentBriefCandidate,
  ConflictGateRouteStats,
  ConflictGateStatus,
  ConflictGateValidationReport,
  TimeframeDecision,
} from "@/types/generated/api";

const DEFAULT_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"];
const CHART_TIMEFRAMES: ChartTimeframe[] = ["15m", "1h", "4h", "1d", "1w"];

function clampScore(value?: number | null) {
  if (value == null || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function formatNumber(value?: number | null, digits = 2) {
  if (value == null || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits === 0 ? 0 : undefined,
  }).format(value);
}

function formatCompactNumber(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 1)}%`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function directionTone(value?: string | null) {
  const normalized = value?.toLowerCase();
  if (normalized === "bullish" || normalized === "allow" || normalized === "ok") {
    return "border-emerald-300/35 bg-emerald-400/10 text-emerald-200";
  }
  if (normalized === "bearish" || normalized === "block" || normalized === "blocked") {
    return "border-rose-300/35 bg-rose-400/10 text-rose-200";
  }
  return "border-cyan-300/25 bg-cyan-400/8 text-cyan-100";
}

function roleTone(role: string) {
  if (role === "trade") return "border-emerald-300/25 bg-emerald-400/10 text-emerald-100";
  if (role === "liquidity") return "border-cyan-300/25 bg-cyan-400/10 text-cyan-100";
  if (role === "macro") return "border-amber-300/25 bg-amber-400/10 text-amber-100";
  return "border-white/15 bg-white/5 text-white/65";
}

function getString(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value.length > 0) return value;
    if (typeof value === "number") return String(value);
  }
  return "--";
}

function traceVisibleKey(row: Record<string, unknown>) {
  return [
    getString(row, ["symbol", "asset"]),
    getString(row, ["action", "decision", "paper_action"]),
    getString(row, ["reason", "blocked_by", "status"]),
  ].join("|");
}

function compactTraceRows(rows: Record<string, unknown>[]) {
  const grouped = new Map<string, { key: string; row: Record<string, unknown>; count: number }>();

  rows.slice(0, 5).forEach((row) => {
    const key = traceVisibleKey(row);
    const existing = grouped.get(key);
    if (existing) {
      existing.count += 1;
      return;
    }
    grouped.set(key, { key, row, count: 1 });
  });

  return Array.from(grouped.values());
}

function LabMetric({
  label,
  value,
  detail,
  tone = "text-white",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/24 p-3">
      <div className="text-[10px] uppercase tracking-widest text-white/38">{label}</div>
      <div className={`mt-2 font-display text-2xl leading-none tabular-nums ${tone}`}>
        {value}
      </div>
      {detail ? <div className="mt-2 text-xs leading-5 text-white/48">{detail}</div> : null}
    </div>
  );
}

function StatusPill({ value }: { value?: string | null }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest ${directionTone(
        value,
      )}`}
    >
      {value ?? "--"}
    </span>
  );
}

function ScoreBar({
  label,
  value,
  detail,
}: {
  label: string;
  value?: number | null;
  detail?: string;
}) {
  const score = clampScore(value);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-semibold text-white/78">{label}</span>
        <span className="font-mono text-cyan-100">{value == null ? "--" : Math.round(value)}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/8">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 0.9, ease: "easeOut" }}
          className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-emerald-300 to-amber-200"
        />
      </div>
      {detail ? <div className="mt-2 text-[11px] text-white/42">{detail}</div> : null}
    </div>
  );
}

function TimeframeCard({
  timeframe,
  frame,
}: {
  timeframe: string;
  frame?: AssetAnalysisTimeframe;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/22 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-display text-sm uppercase tracking-widest text-white/78">
          {timeframe}
        </span>
        <StatusPill value={frame?.direction ?? frame?.status} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-white/35">Score</div>
          <div className="mt-1 font-mono text-cyan-100">{formatNumber(frame?.score, 0)}</div>
        </div>
        <div>
          <div className="text-white/35">RSI</div>
          <div className="mt-1 font-mono text-white/82">{formatNumber(frame?.rsi, 1)}</div>
        </div>
        <div>
          <div className="text-white/35">EMA</div>
          <div className="mt-1 font-mono text-white/82">{frame?.ema_stack ?? "--"}</div>
        </div>
        <div>
          <div className="text-white/35">ATR</div>
          <div className="mt-1 font-mono text-white/82">{formatNumber(frame?.atr, 2)}</div>
        </div>
      </div>
    </div>
  );
}

function buildLayer2ChartGeometry(bars: ChartBar[]) {
  const visible = bars.slice(-96);
  if (visible.length === 0) {
    return {
      visible,
      points: [],
      closePath: "",
      yTicks: [],
      candleWidth: 4,
      latestY: 0,
      rangeHigh: null,
      rangeLow: null,
    };
  }
  const rangeHigh = Math.max(...visible.map((bar) => bar.high));
  const rangeLow = Math.min(...visible.map((bar) => bar.low));
  const rawRange = Math.max(rangeHigh - rangeLow, Math.abs(rangeHigh) * 0.002, 1);
  const topBound = rangeHigh + rawRange * 0.08;
  const lowBound = rangeLow - rawRange * 0.08;
  const priceTop = 24;
  const priceHeight = 198;
  const volumeBase = 298;
  const volumeHeight = 44;
  const left = 38;
  const width = 824;
  const maxVolume = Math.max(1, ...visible.map((bar) => bar.volume ?? 0));
  const yFor = (value: number) =>
    priceTop + ((topBound - value) / Math.max(topBound - lowBound, 0.000001)) * priceHeight;
  const points = visible.map((bar, index) => {
    const x = left + (visible.length === 1 ? width / 2 : (index / (visible.length - 1)) * width);
    return {
      bar,
      x,
      openY: yFor(bar.open),
      highY: yFor(bar.high),
      lowY: yFor(bar.low),
      closeY: yFor(bar.close),
      volumeY: volumeBase - ((bar.volume ?? 0) / maxVolume) * volumeHeight,
      volumeHeight: ((bar.volume ?? 0) / maxVolume) * volumeHeight,
      up: bar.close >= bar.open,
    };
  });
  const closePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.closeY.toFixed(1)}`)
    .join(" ");
  const latest = points[points.length - 1];
  const yTicks = [topBound, (topBound + lowBound) / 2, lowBound].map((value) => ({
    value,
    y: yFor(value),
  }));

  return {
    visible,
    points,
    closePath,
    yTicks,
    candleWidth: Math.max(3, Math.min(9, width / Math.max(visible.length, 1) * 0.54)),
    latestY: latest?.closeY ?? 0,
    rangeHigh,
    rangeLow,
  };
}

type ExchangeChartPoint = CandlestickData<Time> & {
  volume?: number | null;
};

type ExchangeHoverBar = {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
};

type ChartWindowMode = "fit" | "90" | "180";

function toUtcTimestamp(value: string): UTCTimestamp | null {
  const ms = new Date(value).getTime();
  if (!Number.isFinite(ms)) return null;
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function toExchangeChartData(bars: ChartBar[]) {
  const byTime = new Map<number, ExchangeChartPoint>();
  bars.forEach((bar) => {
    const time = toUtcTimestamp(bar.ts);
    if (time == null) return;
    byTime.set(time as number, {
      time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume ?? null,
    });
  });
  return [...byTime.values()].sort((a, b) => Number(a.time) - Number(b.time));
}

function formatChartTime(value?: Time | null) {
  if (value == null) return "--";
  if (typeof value === "number") return formatDateTime(new Date(value * 1000).toISOString());
  if (typeof value === "string") return formatDateTime(value);
  return `${String(value.day).padStart(2, "0")}/${String(value.month).padStart(2, "0")} ${value.year}`;
}

function latestChartWindowRange(length: number, mode: ChartWindowMode, compact = false) {
  if (mode === "fit") return null;
  const size = mode === "90" ? (compact ? 45 : 90) : compact ? 90 : 180;
  return {
    from: Math.max(0, length - size),
    to: length + (compact ? 4 : 8),
  };
}

type Layer2AssetPanelProps = {
  selectedSymbol: string;
};

type Layer2AssetOption = {
  symbol: string;
  label: string;
  kind: string;
  roles: string[];
  price?: number | null;
  score?: number | null;
  direction?: string | null;
  action?: string | null;
  source: string;
  order: number;
};

function normalizeSymbol(symbol?: string | null) {
  return (symbol ?? "").trim().toUpperCase();
}

function resolveActiveSymbol(selectedSymbol?: string | null) {
  return normalizeSymbol(selectedSymbol) || DEFAULT_SYMBOLS[0];
}

function rowMatchesSymbol(row: Record<string, unknown>, symbol: string) {
  const normalized = normalizeSymbol(symbol);
  return ["symbol", "asset", "asset_code"].some(
    (key) => normalizeSymbol(String(row[key] ?? "")) === normalized,
  );
}

function textMentionsSymbol(symbol: string, ...values: Array<string | null | undefined>) {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) return false;
  return values.some((value) => normalizeSymbol(value).includes(normalized));
}

function bestCandidateBySymbol(candidates: AgentBriefCandidate[]) {
  return candidates.reduce<Record<string, AgentBriefCandidate>>((acc, candidate) => {
    const symbol = normalizeSymbol(candidate.symbol);
    if (!symbol) return acc;
    const current = acc[symbol];
    if (!current || (candidate.score ?? 0) > (current.score ?? 0)) acc[symbol] = candidate;
    return acc;
  }, {});
}

function bestMatrixBySymbol(cells: TimeframeDecision[]) {
  return cells.reduce<Record<string, TimeframeDecision>>((acc, cell) => {
    const symbol = normalizeSymbol(cell.symbol);
    if (!symbol) return acc;
    const current = acc[symbol];
    if (!current || (cell.score ?? 0) > (current.score ?? 0)) acc[symbol] = cell;
    return acc;
  }, {});
}

export function Layer2SoulAssetStrip({
  brief,
  selectedSymbol,
  onSelectSymbol,
}: {
  brief: AgentBrief;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}) {
  const registry = useAssetRegistry();
  const snapshot = useDataSnapshot();
  const decisionMatrix = useDecisionMatrix();
  const regime = useRegimeReport();
  const options = useMemo(() => {
    const registryBy = new Map(
      (registry.data?.assets ?? []).map((asset) => [normalizeSymbol(asset.symbol), asset]),
    );
    const priceBy = new Map(
      (snapshot.data?.prices ?? [])
        .filter((price) => price.price != null && Number.isFinite(price.price))
        .map((price) => [normalizeSymbol(price.symbol), price.price]),
    );
    const candidatesBy = bestCandidateBySymbol(brief.top_candidates ?? []);
    const matrixBy = bestMatrixBySymbol(decisionMatrix.data?.cells ?? []);
    const map = new Map<string, Layer2AssetOption>();
    const add = (symbolInput: string | undefined | null, source: string, order: number) => {
      const symbol = normalizeSymbol(symbolInput);
      if (!symbol) return;
      const registryItem = registryBy.get(symbol);
      const candidate = candidatesBy[symbol];
      const matrix = matrixBy[symbol];
      const current = map.get(symbol);
      map.set(symbol, {
        symbol,
        label: registryItem?.label ?? symbol,
        kind: registryItem?.kind ?? "asset",
        roles: registryItem?.roles ?? [],
        price: priceBy.get(symbol) ?? current?.price ?? null,
        score: candidate?.score ?? matrix?.score ?? current?.score ?? null,
        direction: candidate?.direction ?? matrix?.direction ?? current?.direction ?? null,
        action:
          candidate?.final_action ??
          candidate?.candidate_action ??
          matrix?.action ??
          current?.action ??
          null,
        source: current?.source ?? source,
        order: Math.min(current?.order ?? order, order),
      });
    };

    (brief.top_candidates ?? []).forEach((candidate, index) => add(candidate.symbol, "layer1", index));
    (decisionMatrix.data?.symbols ?? []).forEach((symbol, index) => add(symbol, "matrix", 50 + index));
    (registry.data?.trade ?? []).forEach((symbol, index) => add(symbol, "registry", 100 + index));
    (registry.data?.custom ?? []).forEach((symbol, index) => add(symbol, "custom", 130 + index));
    (regime.data?.assets ?? []).forEach((asset, index) => add(asset.symbol, "liquidity", 180 + index));
    DEFAULT_SYMBOLS.forEach((symbol, index) => add(symbol, "default", 220 + index));

    return [...map.values()].sort((a, b) => {
      const scoreDelta = (b.score ?? -1) - (a.score ?? -1);
      if (Math.abs(scoreDelta) > 0.001) return scoreDelta;
      return a.order - b.order;
    });
  }, [
    brief.top_candidates,
    decisionMatrix.data?.cells,
    decisionMatrix.data?.symbols,
    regime.data?.assets,
    registry.data?.assets,
    registry.data?.custom,
    registry.data?.trade,
    snapshot.data?.prices,
  ]);
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const active = options.find((option) => option.symbol === activeSymbol) ?? options[0];

  useEffect(() => {
    if (active && active.symbol !== activeSymbol) onSelectSymbol(active.symbol);
  }, [active, activeSymbol, onSelectSymbol]);

  return (
    <section className="layer2-soul-asset-strip">
      <div className="layer2-soul-asset-head">
        <div>
          <div className="layer2-soul-kicker">Soul asset scope</div>
          <h3>{active?.symbol ?? activeSymbol}</h3>
          <p>
            Katman 1 asset kartlarindaki evren burada secilir. Alttaki tum Soul
            panelleri sadece secili asseti okur.
          </p>
        </div>
        <div className="layer2-soul-live">
          <span>Fiyat</span>
          <strong>{formatNumber(active?.price, active?.price && active.price >= 100 ? 2 : 4)}</strong>
          <em>{active?.action ?? "watch"}</em>
        </div>
      </div>
      <div className="layer2-soul-asset-grid">
        {options.map((asset) => {
          const activeCard = asset.symbol === activeSymbol;
          return (
            <button
              key={asset.symbol}
              type="button"
              onClick={() => onSelectSymbol(asset.symbol)}
              className={`layer2-soul-asset-card ${activeCard ? "is-active" : ""}`}
            >
              <span>{asset.kind}</span>
              <strong>{asset.symbol}</strong>
              <p>{asset.label}</p>
              <div>
                <b>{asset.score == null ? "--" : Math.round(asset.score)}</b>
                <em>{asset.direction ?? asset.source}</em>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function Layer2AssetDrilldownPanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const registry = useAssetRegistry();
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const activeAsset = registry.data?.assets.find(
    (asset) => normalizeSymbol(asset.symbol) === activeSymbol,
  );
  const analysis = useAssetAnalysis(activeSymbol);
  const session = useMarketSessionAsset(activeSymbol);
  const timeframes = analysis.data?.timeframes ?? {};
  const timeframeEntries = Object.entries(timeframes);
  const momentumEntries = Object.entries(analysis.data?.momentum_pct ?? {});
  const markets = session.data?.asset_context?.relevant_markets ?? [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.25fr_0.9fr]">
        <div className="relative overflow-hidden rounded-2xl border border-cyan-300/18 bg-cyan-300/[0.045] p-4">
          <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-cyan-200/55 to-transparent" />
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.28em] text-cyan-100/55">
                Asset terminal
              </div>
              <h4 className="mt-3 font-display text-3xl leading-none text-white">
                {activeSymbol}
              </h4>
              <div className="mt-2 text-sm text-white/52">
                {activeAsset?.label ?? activeSymbol} / {activeAsset?.kind ?? "asset"}
              </div>
            </div>
            <StatusPill value={analysis.data?.overall_direction} />
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <LabMetric
              label="Price"
              value={formatNumber(analysis.data?.last_price, 2)}
              detail="Backend analysis/asset"
              tone="text-cyan-100"
            />
            <LabMetric
              label="Score"
              value={formatNumber(analysis.data?.overall_score, 0)}
              detail={analysis.data?.available ? "available" : "not available"}
              tone="text-emerald-100"
            />
          </div>
          <div className="mt-4 grid gap-2">
            {momentumEntries.length > 0 ? (
              momentumEntries.map(([window, value]) => (
                <ScoreBar
                  key={window}
                  label={`${window} momentum`}
                  value={value == null ? null : 50 + value}
                  detail={formatPct(value)}
                />
              ))
            ) : (
              <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-white/48">
                Momentum verisi bekleniyor.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
                Timeframe matrix
              </div>
              <div className="mt-1 text-sm text-white/68">1h / 4h / 1d teknik kanit</div>
            </div>
            <div className="h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.8)]" />
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {timeframeEntries.length > 0 ? (
              timeframeEntries.map(([tf, frame]) => (
                <TimeframeCard key={tf} timeframe={tf} frame={frame} />
              ))
            ) : (
              <div className="col-span-full rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/48">
                {analysis.isLoading ? "Teknik analiz okunuyor..." : "Timeframe verisi yok."}
              </div>
            )}
          </div>
          {analysis.data?.note ? (
            <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.035] p-3 text-xs leading-5 text-white/50">
              {analysis.data.note}
            </div>
          ) : null}
        </div>

        <div className="rounded-2xl border border-emerald-300/14 bg-emerald-300/[0.045] p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-emerald-100/55">
                Session gate
              </div>
              <div className="mt-2 text-lg font-semibold text-white">
                {session.data?.decision?.action ?? "--"}
              </div>
              <div className="mt-1 text-xs leading-5 text-white/48">
                {session.data?.decision?.reason ?? session.data?.asset_context?.reason ?? "--"}
              </div>
            </div>
            <StatusPill value={session.data?.asset_context?.session_risk} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <LabMetric
              label="Size"
              value={formatNumber(session.data?.decision?.size_multiplier, 2)}
              detail="multiplier"
              tone="text-emerald-100"
            />
            <LabMetric
              label="Open"
              value={session.data?.asset_context?.any_relevant_market_open ? "YES" : "NO"}
              detail="relevant market"
              tone="text-cyan-100"
            />
          </div>
          <div className="mt-4 space-y-2">
            {markets.slice(0, 4).map((market, index) => (
              <div
                key={`${getString(market, ["market_id", "label"])}-${index}`}
                className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs"
              >
                <span className="text-white/70">{getString(market, ["label", "market_id"])}</span>
                <span className="font-mono text-white/44">
                  {getString(market, ["session_phase", "liquidity_tone"])}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Layer2ExchangeChart({
  bars,
  symbol,
  timeframe,
  isLoading,
  windowMode,
}: {
  bars: ChartBar[];
  symbol: string;
  timeframe: ChartTimeframe;
  isLoading: boolean;
  windowMode: ChartWindowMode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartData = useMemo(() => toExchangeChartData(bars), [bars]);
  const volumeData = useMemo<HistogramData<Time>[]>(
    () =>
      chartData.map((bar) => ({
        time: bar.time,
        value: bar.volume ?? 0,
        color:
          bar.close >= bar.open
            ? "rgba(20, 184, 166, 0.34)"
            : "rgba(244, 63, 94, 0.28)",
      })),
    [chartData],
  );
  const latest = chartData[chartData.length - 1];
  const [hover, setHover] = useState<ExchangeHoverBar | null>(null);
  const display = hover ?? latest ?? null;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartData.length === 0) return;

    const compact = container.clientWidth < 460;
    const precision = latest && Math.abs(latest.close) < 10 ? 4 : 2;
    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "rgba(2, 8, 18, 0)" },
        textColor: "rgba(203, 213, 225, 0.72)",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(45, 212, 191, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.1)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(125, 211, 252, 0.48)",
          labelBackgroundColor: "rgba(8, 47, 73, 0.95)",
        },
        horzLine: {
          color: "rgba(125, 211, 252, 0.35)",
          labelBackgroundColor: "rgba(8, 47, 73, 0.95)",
        },
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.16)",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.16)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: compact ? 4 : 8,
        barSpacing: compact ? 7 : 8,
        fixLeftEdge: false,
        fixRightEdge: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#f43f5e",
      borderUpColor: "#5eead4",
      borderDownColor: "#fb7185",
      wickUpColor: "#99f6e4",
      wickDownColor: "#fecdd3",
      priceLineColor: "rgba(250, 204, 21, 0.76)",
      lastValueVisible: true,
      priceLineVisible: true,
      priceFormat: {
        type: "price",
        precision,
        minMove: precision === 4 ? 0.0001 : 0.01,
      },
    });
    candleSeries.setData(chartData);

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });
    volumeSeries.setData(volumeData);

    const range = latestChartWindowRange(chartData.length, windowMode, compact);
    if (range) chart.timeScale().setVisibleLogicalRange(range);
    else chart.timeScale().fitContent();

    const handleMove = (param: MouseEventParams<Time>) => {
      const data = param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined;
      if (!data) {
        setHover(null);
        return;
      }
      const volume = (param.seriesData.get(volumeSeries) as HistogramData<Time> | undefined)
        ?.value;
      setHover({
        time: data.time,
        open: data.open,
        high: data.high,
        low: data.low,
        close: data.close,
        volume,
      });
    };

    chart.subscribeCrosshairMove(handleMove);
    return () => {
      chart.unsubscribeCrosshairMove(handleMove);
      chart.remove();
    };
  }, [chartData, latest, volumeData, windowMode]);

  return (
    <div className="layer2-exchange-chart">
      <div ref={containerRef} className="layer2-exchange-chart__canvas" />
      {chartData.length === 0 ? (
        <div className="layer2-chart-empty">
          {isLoading ? "Grafik verisi okunuyor..." : "Bu timeframe icin bar verisi yok."}
        </div>
      ) : null}
      <div className="layer2-exchange-tooltip">
        <div>
          <span>{symbol}</span>
          <strong>{timeframe}</strong>
          <em>{formatChartTime(display?.time)}</em>
        </div>
        <dl>
          <div>
            <dt>O</dt>
            <dd>{formatNumber(display?.open, display && Math.abs(display.open) < 10 ? 4 : 2)}</dd>
          </div>
          <div>
            <dt>H</dt>
            <dd>{formatNumber(display?.high, display && Math.abs(display.high) < 10 ? 4 : 2)}</dd>
          </div>
          <div>
            <dt>L</dt>
            <dd>{formatNumber(display?.low, display && Math.abs(display.low) < 10 ? 4 : 2)}</dd>
          </div>
          <div>
            <dt>C</dt>
            <dd>{formatNumber(display?.close, display && Math.abs(display.close) < 10 ? 4 : 2)}</dd>
          </div>
          <div>
            <dt>V</dt>
            <dd>{formatCompactNumber(display?.volume)}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

export function Layer2TechnicalChartPanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("4h");
  const [windowMode, setWindowMode] = useState<ChartWindowMode>("90");
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const chartQuery = useTechnicalChart(activeSymbol, timeframe, 220);
  const snapshot = useDataSnapshot();
  const bars = chartQuery.data?.bars ?? [];
  const visibleBars = bars.slice(-96);
  const latest = bars.length > 0 ? bars[bars.length - 1] : null;
  const previous = bars.length > 1 ? bars[bars.length - 2] : null;
  const firstVisible = visibleBars.length > 0 ? visibleBars[0] : null;
  const rangeHigh = visibleBars.length > 0 ? Math.max(...visibleBars.map((bar) => bar.high)) : null;
  const rangeLow = visibleBars.length > 0 ? Math.min(...visibleBars.map((bar) => bar.low)) : null;
  const changePct =
    firstVisible && latest ? ((latest.close - firstVisible.open) / firstVisible.open) * 100 : null;
  const lastCandlePct =
    latest && previous ? ((latest.close - previous.close) / previous.close) * 100 : null;
  const rangePct =
    latest && rangeHigh != null && rangeLow != null
      ? ((rangeHigh - rangeLow) / latest.close) * 100
      : null;
  const technical = snapshot.data?.technicals_by_tf?.[activeSymbol]?.[timeframe];
  const tableBars = bars.slice(-10).reverse();
  const chartStatus = chartQuery.isError ? "ERROR" : technical?.status ?? "OK";

  return (
    <section className="layer2-chart-panel">
      <div className="layer2-chart-head">
        <div>
          <div className="layer2-soul-kicker">Selected asset chart feed</div>
          <h4>
            {activeSymbol} <span>{timeframe}</span>
          </h4>
          <p>
            OHLCV mumlari, son bar tablosu ve ayni timeframe teknik snapshoti. Sembol
            ustteki Soul asset seciminden gelir.
          </p>
        </div>
        <div className="layer2-chart-tabs" aria-label="Chart timeframe">
          {CHART_TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTimeframe(tf)}
              className={timeframe === tf ? "is-active" : ""}
            >
              {tf}
            </button>
          ))}
        </div>
        <div className="layer2-chart-window-tabs" aria-label="Chart window">
          {[
            ["90", "Son 90"],
            ["180", "Son 180"],
            ["fit", "Tum veri"],
          ].map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setWindowMode(mode as ChartWindowMode)}
              className={windowMode === mode ? "is-active" : ""}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="layer2-chart-layout">
        <div className="layer2-chart-shell">
          <Layer2ExchangeChart
            bars={bars}
            symbol={activeSymbol}
            timeframe={timeframe}
            isLoading={chartQuery.isLoading || chartQuery.isFetching}
            windowMode={windowMode}
          />
        </div>

        <aside className="layer2-chart-side">
          <LabMetric
            label="Last"
            value={formatNumber(latest?.close, 2)}
            detail={formatDateTime(latest?.ts)}
            tone="text-cyan-100"
          />
          <LabMetric
            label="Bars"
            value={formatNumber(chartQuery.data?.bars_used ?? bars.length, 0)}
            detail={chartQuery.data?.source ?? "source pending"}
            tone="text-emerald-100"
          />
          <LabMetric
            label="Visible change"
            value={formatPct(changePct)}
            detail="chart window"
            tone={(changePct ?? 0) >= 0 ? "text-emerald-100" : "text-rose-100"}
          />
          <LabMetric
            label="Last candle"
            value={formatPct(lastCandlePct)}
            detail={latest ? `${formatNumber(latest.open, 2)} -> ${formatNumber(latest.close, 2)}` : "--"}
            tone={(lastCandlePct ?? 0) >= 0 ? "text-emerald-100" : "text-rose-100"}
          />
          <div className="layer2-chart-wide rounded-xl border border-white/10 bg-black/24 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] uppercase tracking-widest text-white/38">
                Snapshot technicals
              </div>
              <StatusPill value={chartStatus} />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-white/35">RSI</div>
                <div className="mt-1 font-mono text-white/82">{formatNumber(technical?.rsi, 1)}</div>
              </div>
              <div>
                <div className="text-white/35">MACD</div>
                <div className="mt-1 font-mono text-white/82">{formatNumber(technical?.macd, 3)}</div>
              </div>
              <div>
                <div className="text-white/35">ATR</div>
                <div className="mt-1 font-mono text-white/82">{formatNumber(technical?.atr, 2)}</div>
              </div>
              <div>
                <div className="text-white/35">EMA</div>
                <div className="mt-1 font-mono text-white/82">{technical?.ema_stack ?? "--"}</div>
              </div>
              <div>
                <div className="text-white/35">Score</div>
                <div className="mt-1 font-mono text-amber-100">{formatNumber(technical?.score, 0)}</div>
              </div>
              <div>
                <div className="text-white/35">Range</div>
                <div className="mt-1 font-mono text-white/82">{formatPct(rangePct)}</div>
              </div>
            </div>
            <div className="mt-3 text-[11px] leading-5 text-white/42">
              Skor kaynagi: data/snapshot TechnicalTf. Mum verisi: technical/chart.
            </div>
          </div>
        </aside>
      </div>

      <div className="layer2-chart-table-wrap">
        <table className="layer2-chart-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Open</th>
              <th>High</th>
              <th>Low</th>
              <th>Close</th>
              <th>Volume</th>
              <th>Bar</th>
            </tr>
          </thead>
          <tbody>
            {tableBars.length > 0 ? (
              tableBars.map((bar) => (
                <tr key={bar.ts}>
                  <td>{formatDateTime(bar.ts)}</td>
                  <td>{formatNumber(bar.open, 2)}</td>
                  <td>{formatNumber(bar.high, 2)}</td>
                  <td>{formatNumber(bar.low, 2)}</td>
                  <td>{formatNumber(bar.close, 2)}</td>
                  <td>{formatCompactNumber(bar.volume)}</td>
                  <td className={bar.close >= bar.open ? "is-up" : "is-down"}>
                    {bar.close >= bar.open ? "UP" : "DOWN"}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7}>
                  {chartQuery.isFetching ? "Bar tablosu okunuyor..." : "Bar tablosu bos."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FibFramePanel({ frame }: { frame?: FibonacciFrame | null }) {
  const levels = frame?.levels ?? [];
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            {frame?.timeframe ?? "--"} fib map
          </div>
          <div className="mt-2 font-display text-xl text-white">
            {frame?.trend_direction ?? "--"} / {frame?.zone ?? "--"}
          </div>
        </div>
        <StatusPill value={frame?.validity} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <LabMetric label="High" value={formatNumber(frame?.swing_high, 2)} tone="text-cyan-100" />
        <LabMetric label="Low" value={formatNumber(frame?.swing_low, 2)} tone="text-emerald-100" />
      </div>
      <div className="mt-4 rounded-xl border border-cyan-300/12 bg-cyan-300/[0.04] p-3">
        <div className="text-[10px] uppercase tracking-widest text-cyan-100/55">Nearest</div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusPill value={frame?.nearest_level?.role} />
          <span className="font-display text-lg text-white">
            {frame?.nearest_level?.label ?? "--"}
          </span>
          <span className="font-mono text-sm text-cyan-100">
            {formatNumber(frame?.nearest_level?.price, 2)}
          </span>
          <span className="text-xs text-white/45">
            {formatPct(frame?.nearest_distance_pct)}
          </span>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {levels.slice(0, 7).map((level, index) => (
          <FibLevelRow key={`${level.label}-${level.role}-${index}`} level={level} />
        ))}
      </div>
    </div>
  );
}

function FibLevelRow({ level }: { level: FibonacciLevel }) {
  const distance = Math.min(100, Math.abs(level.distance_pct ?? 0) * 5);
  const roleClass =
    level.role === "support"
      ? "from-emerald-300 to-cyan-300"
      : "from-amber-200 to-rose-300";
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-display text-white/82">{level.label ?? "--"}</span>
          <span className="uppercase tracking-widest text-white/35">{level.role ?? "--"}</span>
        </div>
        <span className="font-mono text-white/62">{formatNumber(level.price, 2)}</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/8">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(8, 100 - distance)}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className={`h-full rounded-full bg-gradient-to-r ${roleClass}`}
        />
      </div>
    </div>
  );
}

export function Layer2FibonacciLabPanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const insight = useTechnicalInsight(activeSymbol);
  const confluence = insight.data?.fib_confluence;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_0.82fr]">
        <FibFramePanel frame={insight.data?.fib_1d} />
        <FibFramePanel frame={insight.data?.fib_4h} />
        <div className="relative overflow-hidden rounded-2xl border border-cyan-300/18 bg-cyan-300/[0.045] p-4">
          <div className="absolute -right-12 -top-12 h-36 w-36 rounded-full bg-cyan-300/10 blur-2xl" />
          <div className="relative">
            <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
              Confluence core
            </div>
            <div className="mt-3 font-display text-5xl leading-none text-white">
              {formatNumber(insight.data?.fibonacci_score, 0)}
            </div>
            <div className="mt-2 text-sm text-white/50">Fibonacci score</div>
            <div className="mt-5">
              <ScoreBar
                label={confluence?.has_confluence ? "Confluence active" : "Confluence passive"}
                value={confluence?.score}
                detail={confluence?.reason ?? "Backend fib_confluence sonucu bekleniyor."}
              />
            </div>
            <div className="mt-4 grid gap-2">
              {[confluence?.nearest_1d_level, confluence?.nearest_4h_level].map((level, index) => (
                <div
                  key={`${level?.label ?? "level"}-${index}`}
                  className="rounded-lg border border-white/10 bg-black/20 p-3"
                >
                  <div className="text-[10px] uppercase tracking-widest text-white/35">
                    nearest {index === 0 ? "1D" : "4H"}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="font-display text-white">{level?.label ?? "--"}</span>
                    <span className="font-mono text-cyan-100">
                      {formatNumber(level?.price, 2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            {insight.isLoading ? (
              <div className="mt-4 text-xs text-white/42">Fibonacci seviyeleri okunuyor...</div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function ElliottScenarioPanel({ analysis }: { analysis?: ElliottAnalysis | null }) {
  const target = analysis?.target_zone;
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            {(analysis?.timeframe ?? "--").toUpperCase()} elliott senaryosu
          </div>
          <div className="mt-2 font-display text-xl text-white">
            {analysis?.primary_scenario ?? "NO_VALID_COUNT"}
          </div>
        </div>
        <StatusPill value={analysis?.bias} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <LabMetric
          label="Confidence"
          value={formatNumber(analysis?.confidence, 0)}
          tone="text-cyan-100"
        />
        <LabMetric
          label="Invalidation"
          value={formatNumber(analysis?.invalidation_price, 2)}
          tone="text-rose-100"
        />
      </div>
      {target ? (
        <div className="mt-4 rounded-xl border border-emerald-300/14 bg-emerald-300/[0.04] p-3">
          <div className="text-[10px] uppercase tracking-widest text-emerald-100/55">
            Target zone
          </div>
          <div className="mt-2 font-mono text-sm text-white">
            {formatNumber(target[0], 2)} — {formatNumber(target[1], 2)}
          </div>
        </div>
      ) : null}
      <div className="mt-4 grid gap-2">
        {(analysis?.wave_points ?? []).map((wp, index) => (
          <div
            key={`${wp.label}-${index}`}
            className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-xs"
          >
            <span className="flex items-center gap-1.5 font-semibold text-white/78">
              {wp.label}
              {index === 0 ? (
                <span className="rounded bg-cyan-300/15 px-1.5 py-0.5 text-[9px] font-normal uppercase tracking-wider text-cyan-200/70">
                  başlangıç
                </span>
              ) : null}
            </span>
            <span className="font-mono text-cyan-100">
              {formatNumber(wp.price, 2)}
              {wp.bar_index != null ? (
                <span className="ml-1.5 text-white/35">bar #{wp.bar_index}</span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
      {(analysis?.diagnostics ?? []).length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {(analysis?.diagnostics ?? []).map((d, i) => (
            <div
              key={i}
              className="rounded-lg border border-white/10 bg-white/[0.025] px-2.5 py-1.5 text-[11px] leading-snug text-white/55"
            >
              {d}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ZoneRow({ zone }: { zone: PriceZone }) {
  const tone = zone.kind === "support" ? "text-emerald-100" : "text-amber-100";
  return (
    <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
      <span className={`uppercase tracking-widest ${tone}`}>{zone.kind ?? "--"}</span>
      <span className="font-mono text-white/70">
        {formatNumber(zone.price_low, 2)} — {formatNumber(zone.price_high, 2)}
      </span>
      <span className="text-white/40">touches={zone.touches ?? 0}</span>
    </div>
  );
}

function ZoneAnalysisPanel({ analysis }: { analysis?: ZoneAnalysis | null }) {
  const zones = analysis?.zones ?? [];
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            Zone analizi
          </div>
          <div className="mt-2 font-display text-xl text-white">
            {analysis?.location ?? "unknown"}
          </div>
        </div>
        <StatusPill value={analysis?.validity} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <LabMetric
          label="Range high"
          value={formatNumber(analysis?.range_high, 2)}
          tone="text-cyan-100"
        />
        <LabMetric
          label="Range low"
          value={formatNumber(analysis?.range_low, 2)}
          tone="text-emerald-100"
        />
      </div>
      <div className="mt-4 space-y-2">
        {zones.length > 0 ? (
          zones
            .slice()
            .sort((a, b) => (a.distance_pct ?? 0) - (b.distance_pct ?? 0))
            .slice(0, 6)
            .map((zone, index) => <ZoneRow key={`${zone.kind}-${index}`} zone={zone} />)
        ) : (
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3 text-sm text-white/45">
            Zone bulunamadi (supply/demand bu surumun kapsami disinda).
          </div>
        )}
      </div>
      {(analysis?.diagnostics ?? []).length > 0 ? (
        <div className="mt-3 text-xs leading-5 text-white/45">
          {(analysis?.diagnostics ?? []).join(", ")}
        </div>
      ) : null}
    </div>
  );
}

function ShadowEvidenceRow({
  row,
}: {
  row: {
    symbol?: string | null;
    elliott_scenario?: string | null;
    elliott_confidence?: number | null;
    elliott_bias?: string | null;
    historical_edge_sample_count?: number | null;
    historical_edge_win_rate?: number | null;
    historical_edge_confidence?: string | null;
    setup_type?: string | null;
    trade_profile?: string | null;
    mode_filter_passed?: boolean | null;
    mode_filter_blocked_reason?: string | null;
    conflict_final_action?: string | null;
    conflict_blocked_by?: string[];
  };
}) {
  return (
    <div className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.035] p-3 md:grid-cols-[0.5fr_0.9fr_0.9fr_0.9fr_0.9fr]">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">symbol</div>
        <div className="mt-1 font-display text-white">{row.symbol ?? "--"}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">elliott</div>
        <div className="mt-1 font-mono text-cyan-100">
          {row.elliott_scenario ?? "--"} ({formatNumber(row.elliott_confidence, 0)})
        </div>
        <div className="mt-1 text-[11px] text-white/45">{row.elliott_bias ?? "--"}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">historical edge</div>
        <div className="mt-1 font-mono text-emerald-100">
          N={row.historical_edge_sample_count ?? 0} / {formatPct(
            row.historical_edge_win_rate == null ? null : row.historical_edge_win_rate * 100,
          )}
        </div>
        <div className="mt-1 text-[11px] text-white/45">{row.historical_edge_confidence ?? "--"}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">setup / profile</div>
        <div className="mt-1 font-mono text-amber-100">{row.setup_type ?? "--"}</div>
        <div className="mt-1 text-[11px] text-white/45">
          {row.trade_profile ?? "--"} {row.mode_filter_passed === false ? "(mode: blocked)" : ""}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">conflict resolver</div>
        <div className="mt-1 font-mono text-white/82">{row.conflict_final_action ?? "--"}</div>
        <div className="mt-1 text-[11px] text-white/45 truncate">
          {(row.conflict_blocked_by ?? []).join(", ") || "--"}
        </div>
      </div>
    </div>
  );
}

export function Layer2ElliottZoneLabPanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const elliott1d = useElliottScenario(activeSymbol, "1d");
  const elliott4h = useElliottScenario(activeSymbol, "4h");
  const zones = useZoneAnalysis(activeSymbol);
  const shadow = useShadowComparison();
  const shadowRows = (shadow.data?.rows ?? []).filter((row) =>
    rowMatchesSymbol(row as Record<string, unknown>, activeSymbol),
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <ElliottScenarioPanel analysis={elliott1d.data} />
        <ElliottScenarioPanel analysis={elliott4h.data} />
      </div>
      <div className="grid gap-4 xl:grid-cols-1">
        <ZoneAnalysisPanel analysis={zones.data} />
      </div>
      <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
          Shadow kanit ozeti (gozlem modu)
        </div>
        <div className="mt-1 text-xs text-white/45">
          Bu satirlar packages/decision/shadow.py'nin gozlem kaydindan gelir; canli
          karari etkilemez (affect_decision={String(shadow.data?.affect_decision ?? false)}).
        </div>
        <div className="mt-3 space-y-2">
          {shadowRows.length > 0 ? (
            shadowRows.map((row, index) => (
              <ShadowEvidenceRow key={`${row.symbol}-${index}`} row={row} />
            ))
          ) : (
            <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3 text-sm text-white/45">
              Shadow kaydi yok veya henuz uretilmedi.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function VolumePanel({ analysis }: { analysis?: VolumeAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Volume</div>
        <StatusPill value={analysis?.validity} />
      </div>
      <div className="mt-2 font-display text-lg text-white">{analysis?.state ?? "VOLUME_NEUTRAL"}</div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <LabMetric label="Ratio" value={formatNumber(analysis?.volume_ratio, 2)} tone="text-cyan-100" />
        <LabMetric label="Price dir" value={analysis?.price_direction ?? "--"} tone="text-emerald-100" />
      </div>
    </div>
  );
}

function VWAPPanel({ analysis }: { analysis?: VWAPAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">VWAP</div>
        <StatusPill value={analysis?.validity} />
      </div>
      <div className="mt-2 font-display text-lg text-white">{analysis?.location ?? "unknown"}</div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <LabMetric label="VWAP" value={formatNumber(analysis?.session_vwap, 2)} tone="text-cyan-100" />
        <LabMetric label="Deviation" value={formatPct(analysis?.deviation_pct)} tone="text-amber-100" />
      </div>
      <div className="mt-2 text-[11px] text-white/45">
        reclaim={String(analysis?.reclaim ?? false)} / rejection={String(analysis?.rejection ?? false)}
      </div>
    </div>
  );
}

function LiquiditySweepPanel({ analysis }: { analysis?: LiquiditySweepAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Liquidity sweep</div>
        <StatusPill value={analysis?.validity} />
      </div>
      <div className="mt-2 font-display text-lg text-white">{analysis?.state ?? "NO_SWEEP"}</div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <LabMetric label="Swing high" value={formatNumber(analysis?.swing_high, 2)} tone="text-rose-100" />
        <LabMetric label="Swing low" value={formatNumber(analysis?.swing_low, 2)} tone="text-emerald-100" />
      </div>
      <div className="mt-2 text-[11px] text-white/45">bias={analysis?.bias ?? "unknown"}</div>
    </div>
  );
}

function ExhaustionPanel({ analysis }: { analysis?: ExhaustionAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Exhaustion score</div>
        <StatusPill value={analysis?.validity} />
      </div>
      <div className="mt-3">
        <ScoreBar label="0=downside / 100=upside" value={analysis?.score} detail={`RSI ${formatNumber(analysis?.rsi, 1)}`} />
      </div>
      <div className="mt-2 text-[11px] text-white/45">{(analysis?.contributions ?? []).join(", ") || "--"}</div>
    </div>
  );
}

function LocationScorePanel({ analysis }: { analysis?: LocationScoreAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Location score</div>
        <StatusPill value={analysis?.location_class} />
      </div>
      <div className="mt-3">
        <ScoreBar label="0=bad / 100=good" value={analysis?.score} />
      </div>
      <div className="mt-2 text-[11px] text-white/45">{(analysis?.contributions ?? []).join(", ") || "--"}</div>
    </div>
  );
}

function TriggerPanel({ analysis }: { analysis?: TriggerAnalysis | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Trigger engine</div>
        <StatusPill value={analysis?.state} />
      </div>
      <div className="mt-3">
        <ScoreBar label="trigger score" value={analysis?.trigger_score} />
      </div>
      <div className="mt-2 text-[11px] text-white/45">{(analysis?.matched_triggers ?? []).join(", ") || "--"}</div>
    </div>
  );
}

function plainSweepBias(state: string | null | undefined, bias: string | null | undefined): string {
  if (state === "LOW_SWEEP_PENDING") return "likidite süpürmesi (stop avı) henüz olmadı, bekleniyor";
  if (state?.includes("SWEEP") && state?.includes("CONFIRMED")) {
    return `likidite süpürüldü — yön: ${bias === "bullish" ? "yukarı" : bias === "bearish" ? "aşağı" : "belirsiz"}`;
  }
  return "likidite durumu net değil";
}

function plainExhaustion(score: number | null | undefined, rsi: number | null | undefined): string {
  if (score == null) return "tükenme verisi yok";
  if (score >= 70) return `yukarı yönde tükenme belirtisi var (${score}/100)${rsi != null ? `, RSI ${rsi}` : ""}`;
  if (score <= 30) return `aşağı yönde tükenme belirtisi var (${score}/100)${rsi != null ? `, RSI ${rsi}` : ""}`;
  return `ne alıcı ne satıcı tükenmiş — orta bölge (${score}/100)${rsi != null ? `, RSI ${rsi}` : ""}`;
}

function plainLocation(score: number | null | undefined, locationClass: string | null | undefined): string {
  if (score == null) return "konum verisi yok";
  if (score >= 65) return `iyi konum (${score}/100) — destek/direnç netliği var`;
  if (score <= 35) return `kötü konum (${score}/100) — fiyat orta bölgede, ne destekte ne dirençte (${locationClass ?? "mid_range"})`;
  return `orta konum (${score}/100)`;
}

function plainTrigger(state: string | null | undefined, matched: string[] | null | undefined): string {
  if (state === "TRIGGER_MISSING" || !matched || matched.length === 0) {
    return "hiçbir tetikleyici sinyal yok — şimdi gir diyen bir motor yok";
  }
  return `tetikleyici(ler) eşleşti: ${matched.join(", ")}`;
}

function plainVerdict(
  volume?: VolumeAnalysis | null,
  location?: LocationScoreAnalysis | null,
  trigger?: TriggerAnalysis | null,
): string {
  const weakVolume = !volume?.volume_ratio || volume.volume_ratio < 1.2;
  const badLocation = (location?.score ?? 50) <= 35;
  const noTrigger = !trigger?.matched_triggers || trigger.matched_triggers.length === 0;
  if (weakVolume && badLocation && noTrigger) {
    return "Şu an belirsiz/orta bölge: hacim zayıf, konum net değil, tetik yok — sistem bu yüzden işlem açmıyor. Bu, veri eksikliği değil, net bir sinyal olmadığının göstergesi.";
  }
  if (!noTrigger) {
    return "En az bir tetikleyici eşleşti — diğer motorlarla birlikte değerlendirilmeli.";
  }
  return "Karışık sinyaller var — tek bir motor net konuşmuyor.";
}

function PlainLanguageSummary({
  symbol,
  volume,
  vwap,
  sweep,
  exhaustion,
  location,
  trigger,
}: {
  symbol: string;
  volume?: VolumeAnalysis | null;
  vwap?: VWAPAnalysis | null;
  sweep?: LiquiditySweepAnalysis | null;
  exhaustion?: ExhaustionAnalysis | null;
  location?: LocationScoreAnalysis | null;
  trigger?: TriggerAnalysis | null;
}) {
  return (
    <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/[0.04] p-3 text-xs leading-6 text-white/78">
      <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-200/60">
        {symbol} — sade özet
      </div>
      <ul className="mt-1.5 list-disc space-y-1 pl-4">
        <li>Hacim: {volume?.volume_ratio != null ? `${volume.volume_ratio.toFixed(2)}x ortalama — ${volume.volume_ratio < 1.2 ? "yön doğrulayacak kadar güçlü değil" : "güçlü, yönü destekliyor"}` : "veri yok"}.</li>
        <li>VWAP: {vwap?.location && vwap.location !== "unknown" ? `fiyat VWAP'a göre ${vwap.location}` : "hesaplanamadı (yetersiz veri)"}{vwap?.reclaim ? ", reclaim oldu" : ""}{vwap?.rejection ? ", reddedildi" : ""}.</li>
        <li>Likidite: {plainSweepBias(sweep?.state, sweep?.bias)}.</li>
        <li>Tükenme: {plainExhaustion(exhaustion?.score, exhaustion?.rsi)}.</li>
        <li>Konum: {plainLocation(location?.score, location?.location_class)}.</li>
        <li>Tetik: {plainTrigger(trigger?.state, trigger?.matched_triggers)}.</li>
      </ul>
      <div className="mt-2 border-t border-white/10 pt-2 text-white/85">
        {plainVerdict(volume, location, trigger)}
      </div>
    </div>
  );
}

export function Layer2SetupConflictLabPanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const volume = useVolumeAnalysis(activeSymbol);
  const vwap = useVwapAnalysis(activeSymbol);
  const sweep = useLiquiditySweepAnalysis(activeSymbol);
  const exhaustion = useExhaustionScore(activeSymbol);
  const location = useLocationScore(activeSymbol);
  const trigger = useTriggerAnalysis(activeSymbol);

  return (
    <div className="space-y-4">
      <PlainLanguageSummary
        symbol={activeSymbol}
        volume={volume.data}
        vwap={vwap.data}
        sweep={sweep.data}
        exhaustion={exhaustion.data}
        location={location.data}
        trigger={trigger.data}
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <VolumePanel analysis={volume.data} />
        <VWAPPanel analysis={vwap.data} />
        <LiquiditySweepPanel analysis={sweep.data} />
        <ExhaustionPanel analysis={exhaustion.data} />
        <LocationScorePanel analysis={location.data} />
        <TriggerPanel analysis={trigger.data} />
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3 text-xs leading-5 text-white/45">
        Bu altı motor (Volume/VWAP/Liquidity Sweep/Exhaustion/Location/Trigger) EVIDENCE
        only'dir; hiçbir karar zincirine bağlı değildir. Setup Classifier + Conflict
        Resolver çıktısı için "Elliott / Zone Lab" panelindeki Shadow kanıt tablosuna bakın.
      </div>
    </div>
  );
}

function modeTone(mode: string) {
  switch (mode) {
    case "OFF":
      return "text-white/45";
    case "SOFT":
      return "text-cyan-100";
    case "SOFT_PLUS":
      return "text-amber-100";
    case "HARD":
      return "text-orange-100";
    case "HARD_MANUAL":
      return "text-rose-100";
    default:
      return "text-white/72";
  }
}

const PROFILE_ORDER = ["SCALP", "INTRADAY", "TACTICAL", "SWING", "POSITION"];

function ConflictGateStatusPanel({ status }: { status?: ConflictGateStatus | null }) {
  const modes = status?.profile_modes ?? {};
  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">Conflict Gate durumu</div>
        <StatusPill value={status?.enabled ? "ENABLED" : "DISABLED"} />
      </div>
      <div className="mt-2 font-display text-lg text-white">
        {status?.enabled ? "Aktif — eski sistemi süzüyor" : "Kapalı — eski sistem tek başına karar veriyor"}
      </div>
      <div className="mt-3 space-y-1.5">
        {PROFILE_ORDER.filter((p) => modes[p]).map((profile) => (
          <div key={profile} className="flex items-center justify-between text-xs">
            <span className="text-white/55">{profile}</span>
            <span className={`font-mono ${modeTone(modes[profile])}`}>{modes[profile]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConflictGateValidationPanel({ report }: { report?: ConflictGateValidationReport | null }) {
  const unmatched = typeof report?._unmatched_no_shadow_data === "number" ? report._unmatched_no_shadow_data : 0;
  const profiles = PROFILE_ORDER.filter(
    (p) => report && typeof report[p] === "object" && report[p] !== null,
  );

  return (
    <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
      <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
        Faz 9A — retrospektif doğrulama
      </div>
      <div className="mt-1 text-xs text-white/45">
        Gate açık olsaydı bloklanan/küçültülen işlemlerin gerçek win-rate'i ne çıkardı.
      </div>
      <div className="mt-3 space-y-3">
        {profiles.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3 text-sm text-white/45">
            Henüz eşleşen veri yok (shadow gözlem kaydı yetersiz).
          </div>
        ) : (
          profiles.map((profile) => {
            const routes = report?.[profile] as Record<string, ConflictGateRouteStats>;
            return (
              <div key={profile}>
                <div className="text-[11px] uppercase tracking-widest text-white/55">{profile}</div>
                <div className="mt-1 grid gap-1.5">
                  {Object.entries(routes).map(([route, stats]) => (
                    <div
                      key={route}
                      className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs"
                    >
                      <span className="font-mono text-white/72">{route}</span>
                      <span className="text-white/45">
                        n={stats.n} · winrate={formatPct(stats.win_rate * 100)} · avgPnL=
                        {formatNumber(stats.avg_pnl, 2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })
        )}
        <div className="text-[11px] text-white/35">_unmatched_no_shadow_data = {unmatched}</div>
      </div>
    </div>
  );
}

export function Layer2ConflictGateLabPanel() {
  const status = useConflictGateStatus();
  const validation = useConflictGateValidation();

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <ConflictGateStatusPanel status={status.data} />
        <ConflictGateValidationPanel report={validation.data} />
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3 text-xs leading-5 text-white/45">
        Conflict Gate (Faz 8), eski sistemin (decide_matrix) önerisini Conflict Resolver'ın
        verdict'iyle trade_profile bazlı kademeli sıkılıkla birleştirir — packages/decision/gates.py
        TEK rotalama noktasıdır. enabled=false olduğu sürece davranış değişmez (fail-open).
      </div>
    </div>
  );
}

function BacktestMetricGrid({
  metrics,
}: {
  metrics?: {
    signals_evaluated?: number;
    hit_rate?: number | null;
    false_positive_rate?: number | null;
    blocked_decision_accuracy?: number | null;
    max_drawdown?: number | null;
    avg_return?: number | null;
  };
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <LabMetric
        label="Signals"
        value={formatNumber(metrics?.signals_evaluated, 0)}
        detail="evaluated"
        tone="text-cyan-100"
      />
      <LabMetric
        label="Hit rate"
        value={formatPct(metrics?.hit_rate == null ? null : metrics.hit_rate * 100)}
        detail="rolling outcome"
        tone="text-emerald-100"
      />
      <LabMetric
        label="False positive"
        value={formatPct(
          metrics?.false_positive_rate == null ? null : metrics.false_positive_rate * 100,
        )}
        detail="suppression quality"
        tone="text-amber-100"
      />
      <LabMetric
        label="Blocked accuracy"
        value={formatPct(
          metrics?.blocked_decision_accuracy == null
            ? null
            : metrics.blocked_decision_accuracy * 100,
        )}
        detail="risk gate read"
        tone="text-cyan-100"
      />
      <LabMetric
        label="Max DD"
        value={formatPct(metrics?.max_drawdown == null ? null : metrics.max_drawdown * 100)}
        detail="snapshot series"
        tone="text-rose-100"
      />
      <LabMetric
        label="Avg return"
        value={formatPct(metrics?.avg_return == null ? null : metrics.avg_return * 100)}
        detail="backend replay"
        tone="text-white"
      />
    </div>
  );
}

export function Layer2BacktestOutcomePanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const replayStatus = useReplayStatus();
  const trace = useReplayDecisionTrace(replayStatus.data?.latest_snapshot_id);
  const backtest = useReplayBacktest();
  const topCandidates = (trace.data?.top_candidates ?? []).filter((row) =>
    rowMatchesSymbol(row as Record<string, unknown>, activeSymbol),
  );
  const finalDecisions = (trace.data?.final_decisions ?? []).filter((row) =>
    rowMatchesSymbol(row as Record<string, unknown>, activeSymbol),
  );
  const errorText = backtest.error instanceof Error ? backtest.error.message : null;

  return (
    <div className="grid gap-4 xl:grid-cols-[0.85fr_1.25fr]">
      <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
              Replay store
            </div>
            <div className="mt-2 font-display text-2xl text-white">
              {replayStatus.data?.status ?? "status"}
            </div>
            <div className="mt-1 text-sm text-white/48">
              {replayStatus.data?.snapshot_count ?? 0} snapshot / latest{" "}
              {replayStatus.data?.latest_snapshot_id ?? "--"}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void backtest.refetch()}
            disabled={backtest.isFetching}
            className="rounded-xl border border-cyan-300/28 bg-cyan-300/10 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-cyan-100 transition hover:border-cyan-200/55 disabled:cursor-wait disabled:opacity-60"
          >
            {backtest.isFetching ? "running" : "run backtest"}
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <LabMetric
            label="Mode"
            value={replayStatus.data?.mode ?? "--"}
            detail={replayStatus.data?.available ? "available" : "unavailable"}
            tone="text-cyan-100"
          />
          <LabMetric
            label="Schema"
            value={formatNumber(replayStatus.data?.schema_version, 0)}
            detail={formatDateTime(replayStatus.data?.latest_generated_at)}
            tone="text-white"
          />
        </div>
        {errorText ? (
          <div className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/8 p-3 text-xs leading-5 text-amber-100/80">
            Backtest endpoint cevap vermedi veya zaman asimina dustu. Trace ve store durumu yine
            okunuyor; agir test manuel kalacak.
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-cyan-300/14 bg-cyan-300/[0.035] p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
              {activeSymbol} outcome metrics
            </div>
            <div className="mt-1 text-sm text-white/55">
              Secili asset icin deterministic rolling backtest ve son karar izi
            </div>
          </div>
          <StatusPill value={backtest.data?.status ?? trace.data?.note ?? "trace"} />
        </div>
        <div className="mt-4">
          <BacktestMetricGrid metrics={backtest.data?.metrics} />
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-black/22 p-4 xl:col-span-2">
        <div className="grid gap-4 lg:grid-cols-2">
          <TraceList
            title={`${activeSymbol} top candidates`}
            rows={topCandidates}
            emptyText="Son snapshot icin aday yok veya trace bekleniyor."
          />
          <TraceList
            title={`${activeSymbol} final decisions`}
            rows={finalDecisions}
            emptyText="Final decision kaydi yok."
          />
        </div>
      </div>
    </div>
  );
}

function TraceList({
  title,
  rows,
  emptyText,
}: {
  title: string;
  rows: Record<string, unknown>[];
  emptyText: string;
}) {
  const compactRows = compactTraceRows(rows);
  const visibleCount = Math.min(rows.length, 5);

  return (
    <section className="layer2-trace-list">
      <div className="layer2-trace-list__head">
        <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">{title}</div>
        <span>
          {rows.length > 0
            ? `${visibleCount} kayit / ${compactRows.length} grup`
            : "trace bekleniyor"}
        </span>
      </div>

      <div className="mt-3 space-y-2">
        {compactRows.map((item) => (
          <TraceRow key={item.key} row={item.row} count={item.count} />
        ))}
        {rows.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
            {emptyText}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function TraceRow({ row, count }: { row: Record<string, unknown>; count: number }) {
  const symbol = getString(row, ["symbol", "asset"]);
  const action = getString(row, ["action", "decision", "paper_action"]);
  const reason = getString(row, ["reason", "blocked_by", "status"]);

  return (
    <div className="layer2-trace-row">
      <div className="layer2-trace-cell layer2-trace-cell--symbol">
        <span>symbol</span>
        <strong>{symbol}</strong>
      </div>
      <div className="layer2-trace-cell">
        <span>action</span>
        <strong className={action === "--" ? "text-white/45" : "text-cyan-100"}>{action}</strong>
        {count > 1 ? <em>{count} kayit</em> : null}
      </div>
      <div className="layer2-trace-cell layer2-trace-cell--reason">
        <span>reason</span>
        <div title={reason}>
          {reason}
        </div>
      </div>
    </div>
  );
}

export function Layer2SystemBriefArchivePanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const briefing = useAgentBriefing();
  const notifications = useNotifications();
  const health = useSystemHealth();
  const headlines = (briefing.data?.headlines ?? []).filter((headline) =>
    textMentionsSymbol(activeSymbol, headline.title, headline.detail, headline.category),
  );
  const assetNotifications = (notifications.data?.notifications ?? []).filter((notification) =>
    textMentionsSymbol(activeSymbol, notification.title, notification.body_short, notification.body_long),
  );
  const workers = Object.entries(health.data?.workers ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="rounded-2xl border border-cyan-300/14 bg-cyan-300/[0.035] p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
              {activeSymbol} archive
            </div>
            <h4 className="mt-2 font-display text-2xl text-white">
              {headlines[0]?.title ?? `${activeSymbol} icin ozel brief yok`}
            </h4>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/54">
              {headlines[0]?.detail ??
                "Genel agent brief okunuyor; bu panel sadece secili assete temas eden headline ve bildirimi gosterir."}
            </p>
          </div>
          <StatusPill value={briefing.data?.executive?.tone ?? briefing.data?.engine?.status} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <LabMetric
            label="Stance"
            value={briefing.data?.executive?.stance_label ?? "--"}
            detail={briefing.data?.regime_label ?? "regime"}
            tone="text-cyan-100"
          />
          <LabMetric
            label="DQS"
            value={formatNumber(briefing.data?.dqs?.score, 0)}
            detail={briefing.data?.dqs?.status}
            tone="text-emerald-100"
          />
          <LabMetric
            label="Cycles"
            value={formatNumber(briefing.data?.engine?.cycle_count, 0)}
            detail={briefing.data?.engine?.stale ? "stale" : "fresh"}
            tone="text-white"
          />
        </div>
        <div className="mt-4 space-y-2">
          {headlines.slice(0, 5).map((headline, index) => (
            <div
              key={`${headline.category}-${headline.title}-${index}`}
              className="rounded-xl border border-white/10 bg-black/20 p-3"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] uppercase tracking-widest text-cyan-100/50">
                  {headline.category}
                </span>
                <StatusPill value={headline.tone} />
              </div>
              <div className="mt-2 font-semibold text-white/86">{headline.title}</div>
              {headline.detail ? (
                <div className="mt-1 text-xs leading-5 text-white/48">{headline.detail}</div>
              ) : null}
            </div>
          ))}
          {headlines.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/45">
              {activeSymbol} icin asset-ozel headline yok.
            </div>
          ) : null}
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            Notification stream
          </div>
          <div className="mt-3 space-y-2">
            {assetNotifications.slice(0, 5).map((notification) => (
              <div key={notification.id} className="rounded-xl border border-white/10 bg-white/[0.035] p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-white/82">{notification.title}</span>
                  <StatusPill value={notification.priority} />
                </div>
                <div className="mt-1 text-xs leading-5 text-white/48">
                  {notification.body_short}
                </div>
              </div>
            ))}
            {assetNotifications.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
                {activeSymbol} icin bildirim yok.
              </div>
            ) : null}
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            Worker memory
          </div>
          <div className="mt-3 space-y-2">
            {workers.map(([name, worker]) => (
              <div key={name} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-xs">
                <span className="text-white/70">{name}</span>
                <span className="font-mono text-cyan-100">{worker?.status ?? "--"}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 text-xs leading-5 text-white/45">
            Last tick: {formatDateTime(health.data?.last_successful_tick)} / learning:{" "}
            {formatDateTime(health.data?.last_learning_run)}
          </div>
        </div>
      </div>
    </div>
  );
}

export function Layer2AssetUniversePanel({ selectedSymbol }: Layer2AssetPanelProps) {
  const registry = useAssetRegistry();
  const snapshot = useDataSnapshot();
  const activeSymbol = resolveActiveSymbol(selectedSymbol);
  const assets = registry.data?.assets ?? [];
  const activeAsset = assets.find((asset) => normalizeSymbol(asset.symbol) === activeSymbol);
  const livePrice = snapshot.data?.prices.find((price) => normalizeSymbol(price.symbol) === activeSymbol);
  const roleBuckets = [
    { label: "Trade", symbols: registry.data?.trade ?? [] },
    { label: "Snapshot", symbols: registry.data?.snapshot ?? [] },
    { label: "Liquidity", symbols: registry.data?.liquidity ?? [] },
    { label: "Custom", symbols: registry.data?.custom ?? [] },
  ];
  const activeBuckets = roleBuckets.filter((bucket) =>
    bucket.symbols.some((symbol) => normalizeSymbol(symbol) === activeSymbol),
  );
  const priceText = formatNumber(livePrice?.price, livePrice?.price && livePrice.price >= 100 ? 2 : 4);
  const dqsText = formatNumber(snapshot.data?.dqs?.score, 0);
  const registryStatus = registry.isLoading ? "loading" : "ready";

  return (
    <div className="layer2-universe-record rounded-2xl border border-cyan-300/14 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
            {activeSymbol} universe record
          </div>
          <div className="mt-1 text-sm text-white/55">
            Registry rolleri, bucket kaydi, snapshot fiyati ve DQS
          </div>
        </div>
        <StatusPill value={registryStatus} />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[0.8fr_0.8fr_1.35fr]">
        <div className="layer2-universe-stat">
          <span>Price</span>
          <strong className="text-cyan-100">{priceText}</strong>
          <em>{livePrice?.status ?? "snapshot"}</em>
        </div>

        <div className="layer2-universe-stat">
          <span>DQS</span>
          <strong className="text-emerald-100">{dqsText}</strong>
          <em>{snapshot.data?.dqs?.status ?? "--"}</em>
        </div>

        <div className="layer2-universe-taxonomy">
          <div>
            <span>Selected asset taxonomy</span>
            <p>Backend registry kaydindan secili assetin rolleri</p>
          </div>
          {activeAsset ? (
            <>
              <div className="layer2-universe-identity">
                <span className="font-display text-xl uppercase tracking-widest text-white">
                  {activeAsset.symbol}
                </span>
                <span className="text-sm text-white/48">{activeAsset.label}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-white/65">
                  {activeAsset.kind}
                </span>
                {activeAsset.roles.map((role) => (
                  <span key={`${activeAsset.symbol}-${role}`} className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest ${roleTone(role)}`}>
                    {role}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
              {activeSymbol} registry kaydi yok.
            </div>
          )}
        </div>
      </div>

      <div className="layer2-universe-buckets mt-3">
        <span>Registry buckets</span>
        <strong>{activeSymbol}</strong>
        <div>
          {activeBuckets.map((bucket) => (
            <em key={bucket.label}>{bucket.label}</em>
          ))}
        </div>
        {activeBuckets.length === 0 ? (
          <p>
            {activeSymbol} registry bucket'larinda bulunmuyor; yine de live/technical endpointleri okunur.
          </p>
        ) : null}
      </div>
    </div>
  );
}
