"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";

import type {
  AssetAnalysisTimeframe,
  AssetRegistryItem,
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
  useDataSnapshot,
  useElliottScenario,
  useExhaustionScore,
  useLiquiditySweepAnalysis,
  useLocationScore,
  useMarketSessionAsset,
  useNotifications,
  useReplayBacktest,
  useReplayDecisionTrace,
  useReplayStatus,
  useShadowComparison,
  useSystemHealth,
  useTechnicalInsight,
  useTriggerAnalysis,
  useVolumeAnalysis,
  useVwapAnalysis,
  useZoneAnalysis,
} from "@/lib/queries/hooks";

const DEFAULT_SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD"];

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

function AssetSelector({
  assets,
  activeSymbol,
  onSelect,
}: {
  assets: AssetRegistryItem[];
  activeSymbol: string;
  onSelect: (symbol: string) => void;
}) {
  const visibleAssets =
    assets.length > 0
      ? assets
      : DEFAULT_SYMBOLS.map((symbol) => ({
          symbol,
          label: symbol,
          kind: "trade",
          roles: ["trade"],
        }));

  return (
    <div className="flex flex-wrap gap-2">
      {visibleAssets.map((asset) => {
        const active = asset.symbol === activeSymbol;
        return (
          <button
            key={asset.symbol}
            type="button"
            onClick={() => onSelect(asset.symbol)}
            className={`rounded-xl border px-3 py-2 text-left transition ${
              active
                ? "border-cyan-300/55 bg-cyan-300/14 text-white shadow-[0_0_24px_rgba(34,211,238,0.16)]"
                : "border-white/10 bg-white/[0.035] text-white/62 hover:border-cyan-300/28 hover:text-white"
            }`}
          >
            <div className="font-display text-sm leading-none">{asset.symbol}</div>
            <div className="mt-1 text-[10px] uppercase tracking-widest text-white/38">
              {asset.label} / {asset.kind}
            </div>
          </button>
        );
      })}
    </div>
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

function selectedAssetList(registryAssets?: AssetRegistryItem[], symbols?: string[]) {
  const assets = registryAssets ?? [];
  if (symbols?.length) {
    return symbols.map((symbol) => {
      return (
        assets.find((asset) => asset.symbol === symbol) ?? {
          symbol,
          label: symbol,
          kind: "trade",
          roles: ["trade"],
        }
      );
    });
  }
  return assets;
}

export function Layer2AssetDrilldownPanel() {
  const registry = useAssetRegistry();
  const [selected, setSelected] = useState("BTCUSD");
  const tradeAssets = selectedAssetList(registry.data?.assets, registry.data?.trade);
  const activeSymbol =
    tradeAssets.some((asset) => asset.symbol === selected) || tradeAssets.length === 0
      ? selected
      : tradeAssets[0].symbol;
  const activeAsset = tradeAssets.find((asset) => asset.symbol === activeSymbol);
  const analysis = useAssetAnalysis(activeSymbol);
  const session = useMarketSessionAsset(activeSymbol);
  const timeframes = analysis.data?.timeframes ?? {};
  const timeframeEntries = Object.entries(timeframes);
  const momentumEntries = Object.entries(analysis.data?.momentum_pct ?? {});
  const markets = session.data?.asset_context?.relevant_markets ?? [];

  return (
    <div className="space-y-4">
      <AssetSelector assets={tradeAssets} activeSymbol={activeSymbol} onSelect={setSelected} />

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

export function Layer2FibonacciLabPanel() {
  const registry = useAssetRegistry();
  const [selected, setSelected] = useState("BTCUSD");
  const tradeAssets = selectedAssetList(registry.data?.assets, registry.data?.trade);
  const activeSymbol =
    tradeAssets.some((asset) => asset.symbol === selected) || tradeAssets.length === 0
      ? selected
      : tradeAssets[0].symbol;
  const insight = useTechnicalInsight(activeSymbol);
  const confluence = insight.data?.fib_confluence;

  return (
    <div className="space-y-4">
      <AssetSelector assets={tradeAssets} activeSymbol={activeSymbol} onSelect={setSelected} />
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
            Elliott senaryosu
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
            <span className="font-semibold text-white/78">{wp.label}</span>
            <span className="font-mono text-cyan-100">{formatNumber(wp.price, 2)}</span>
          </div>
        ))}
      </div>
      {(analysis?.diagnostics ?? []).length > 0 ? (
        <div className="mt-3 text-xs leading-5 text-white/45">
          {(analysis?.diagnostics ?? []).join(", ")}
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

export function Layer2ElliottZoneLabPanel() {
  const registry = useAssetRegistry();
  const [selected, setSelected] = useState("BTCUSD");
  const tradeAssets = selectedAssetList(registry.data?.assets, registry.data?.trade);
  const activeSymbol =
    tradeAssets.some((asset) => asset.symbol === selected) || tradeAssets.length === 0
      ? selected
      : tradeAssets[0].symbol;
  const elliott = useElliottScenario(activeSymbol);
  const zones = useZoneAnalysis(activeSymbol);
  const shadow = useShadowComparison();
  const shadowRows = shadow.data?.rows ?? [];

  return (
    <div className="space-y-4">
      <AssetSelector assets={tradeAssets} activeSymbol={activeSymbol} onSelect={setSelected} />
      <div className="grid gap-4 xl:grid-cols-2">
        <ElliottScenarioPanel analysis={elliott.data} />
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

export function Layer2SetupConflictLabPanel() {
  const registry = useAssetRegistry();
  const [selected, setSelected] = useState("BTCUSD");
  const tradeAssets = selectedAssetList(registry.data?.assets, registry.data?.trade);
  const activeSymbol =
    tradeAssets.some((asset) => asset.symbol === selected) || tradeAssets.length === 0
      ? selected
      : tradeAssets[0].symbol;
  const volume = useVolumeAnalysis(activeSymbol);
  const vwap = useVwapAnalysis(activeSymbol);
  const sweep = useLiquiditySweepAnalysis(activeSymbol);
  const exhaustion = useExhaustionScore(activeSymbol);
  const location = useLocationScore(activeSymbol);
  const trigger = useTriggerAnalysis(activeSymbol);

  return (
    <div className="space-y-4">
      <AssetSelector assets={tradeAssets} activeSymbol={activeSymbol} onSelect={setSelected} />
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

export function Layer2BacktestOutcomePanel() {
  const replayStatus = useReplayStatus();
  const trace = useReplayDecisionTrace(replayStatus.data?.latest_snapshot_id);
  const backtest = useReplayBacktest();
  const topCandidates = trace.data?.top_candidates ?? [];
  const finalDecisions = trace.data?.final_decisions ?? [];
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
              Outcome metrics
            </div>
            <div className="mt-1 text-sm text-white/55">
              Deterministic rolling backtest ve son karar izi
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
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
              Top candidates
            </div>
            <div className="mt-3 space-y-2">
              {topCandidates.slice(0, 5).map((candidate, index) => (
                <TraceRow key={`candidate-${index}`} row={candidate} />
              ))}
              {topCandidates.length === 0 ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
                  Son snapshot icin aday yok veya trace bekleniyor.
                </div>
              ) : null}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
              Final decisions
            </div>
            <div className="mt-3 space-y-2">
              {finalDecisions.slice(0, 5).map((decision, index) => (
                <TraceRow key={`decision-${index}`} row={decision} />
              ))}
              {finalDecisions.length === 0 ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
                  Final decision kaydi yok.
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TraceRow({ row }: { row: Record<string, unknown> }) {
  return (
    <div className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.035] p-3 md:grid-cols-[0.7fr_0.7fr_1fr]">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">symbol</div>
        <div className="mt-1 font-display text-white">{getString(row, ["symbol", "asset"])}</div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">action</div>
        <div className="mt-1 font-mono text-cyan-100">
          {getString(row, ["action", "decision", "paper_action"])}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/32">reason</div>
        <div className="mt-1 truncate text-xs text-white/55">
          {getString(row, ["reason", "blocked_by", "status"])}
        </div>
      </div>
    </div>
  );
}

export function Layer2SystemBriefArchivePanel() {
  const briefing = useAgentBriefing();
  const notifications = useNotifications();
  const health = useSystemHealth();
  const headlines = briefing.data?.headlines ?? [];
  const workers = Object.entries(health.data?.workers ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="rounded-2xl border border-cyan-300/14 bg-cyan-300/[0.035] p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
              Executive archive
            </div>
            <h4 className="mt-2 font-display text-2xl text-white">
              {briefing.data?.executive?.headline ?? "Brief bekleniyor"}
            </h4>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/54">
              {briefing.data?.executive?.narrative ?? "Agent briefing endpoint'i okunuyor."}
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
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
            Notification stream
          </div>
          <div className="mt-3 space-y-2">
            {(notifications.data?.notifications ?? []).slice(0, 5).map((notification) => (
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
            {(notifications.data?.notifications ?? []).length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
                Bildirim akisi bos.
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

export function Layer2AssetUniversePanel() {
  const registry = useAssetRegistry();
  const snapshot = useDataSnapshot();
  const assets = registry.data?.assets ?? [];
  const grouped = useMemo(() => {
    return assets.reduce<Record<string, AssetRegistryItem[]>>((acc, asset) => {
      acc[asset.kind] = acc[asset.kind] ?? [];
      acc[asset.kind].push(asset);
      return acc;
    }, {});
  }, [assets]);
  const roleBuckets = [
    { label: "Trade", symbols: registry.data?.trade ?? [] },
    { label: "Snapshot", symbols: registry.data?.snapshot ?? [] },
    { label: "Liquidity", symbols: registry.data?.liquidity ?? [] },
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
      <div className="rounded-2xl border border-cyan-300/14 bg-cyan-300/[0.035] p-4">
        <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">
          Universe map
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <LabMetric
            label="Assets"
            value={formatNumber(assets.length, 0)}
            detail="registry"
            tone="text-cyan-100"
          />
          <LabMetric
            label="DQS"
            value={formatNumber(snapshot.data?.dqs?.score, 0)}
            detail={snapshot.data?.dqs?.status}
            tone="text-emerald-100"
          />
        </div>
        <div className="mt-4 space-y-3">
          {roleBuckets.map((bucket) => (
            <div key={bucket.label} className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-display text-sm uppercase tracking-widest text-white/75">
                  {bucket.label}
                </span>
                <span className="font-mono text-xs text-cyan-100">{bucket.symbols.length}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {bucket.symbols.map((symbol) => (
                  <span key={`${bucket.label}-${symbol}`} className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-semibold text-white/65">
                    {symbol}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-black/22 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] text-white/42">
              Asset taxonomy
            </div>
            <div className="mt-1 text-sm text-white/55">
              Backend registry rollerine gore ayrilmis evren
            </div>
          </div>
          <StatusPill value={registry.isLoading ? "loading" : "ready"} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Object.entries(grouped).map(([kind, kindAssets]) => (
            <div key={kind} className="rounded-xl border border-white/10 bg-white/[0.035] p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-display text-sm uppercase tracking-widest text-white">
                  {kind}
                </span>
                <span className="font-mono text-xs text-white/42">{kindAssets.length}</span>
              </div>
              <div className="mt-3 space-y-2">
                {kindAssets.map((asset) => (
                  <div key={asset.symbol} className="rounded-lg border border-white/10 bg-black/20 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-white/82">{asset.symbol}</span>
                      <span className="text-xs text-white/42">{asset.label}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {asset.roles.map((role) => (
                        <span key={`${asset.symbol}-${role}`} className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest ${roleTone(role)}`}>
                          {role}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {assets.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm text-white/45">
              Asset registry okunuyor.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
