/**
 * HTTP client. Tek `fetchJSON` helper'ı, fetch'in ince sarmalayıcısı.
 * Tüm tipler `types/generated/api.ts`'den gelir.
 */
import type {
  AgentMatrix,
  AIReport,
  ChatResponse,
  CockpitBrief,
  DecisionMatrix,
  CalibrationState,
  ConflictGateStatus,
  ConflictGateValidationReport,
  CorrelationState,
  DashboardState,
  HaltResetResult,
  HaltsState,
  DataSnapshot,
  Health,
  LearningSummary,
  LiquidityRotation,
  MarketSessionsCurrentResponse,
  MistakesState,
  NotificationList,
  PaperTradingState,
  RebalanceState,
  ReplayBacktest,
  ReplayDecisionTrace,
  ReplaySnapshot,
  RegimeReport,
  ReplayStatus,
  ShadowComparison,
  SystemHealth,
  TfWeightsReport,
  TfTargetsView,
  TfTargetsActionResult,
  MissedOpportunitiesView,
  TickResult,
  TradeTicketList,
  AgentBriefing,
  VoiceSpeakRequest,
  AgentQuorumMatrixResponse,
  MarketSessionsTradeUniverseResponse,
} from "@/types/generated/api";

// NEXT_PUBLIC_API_BASE_URL tercih edilen; NEXT_PUBLIC_API_BASE geriye dönük
// uyumluluk için fallback olarak okunur. Boş bırakılırsa same-origin
// (Next.js rewrite /api/* → backend) kullanılır — tek tunnel URL'si yeterli
// olsun diye varsayılan budur.
const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "";

export type ClosePositionResult = {
  status: string;
  position_id: string;
  symbol: string;
  side: string;
  exit_price: number;
  pnl_usd: number;
};

export type UpdateRiskPlanRequest = {
  sl: number | null;
  tp: number | null;
};

export type UpdateRiskPlanResult = {
  status: string;
  position_id: string;
  symbol: string;
  sl: number | null;
  tp: number | null;
  paper_safe?: boolean;
  no_execution?: boolean;
};

export type OrderRequest = {
  symbol: string;
  side: string; // "long" | "short"
  size_usd: number;
  order_type?: string; // market | limit | stop | stop_limit
  entry_price?: number | null;
  limit_price?: number | null;
};

export type OrderResult = {
  status: string;
  kind: string; // market | limit | stop | stop_limit
  symbol: string;
  side: string;
  size_usd: number;
  position_id?: string;
  order_id?: string;
  entry_price?: number;
  trigger_price?: number;
  market?: number;
  sl?: number;
  tp?: number;
};

export type PendingOrder = {
  id: string;
  symbol: string;
  side: string;
  size_usd: number;
  order_type: string;
  trigger_price: number;
  created_at: string;
};

export type AssetRegistryItem = {
  symbol: string;
  label: string;
  kind: string;
  roles: string[];
};

export type AssetRegistry = {
  assets: AssetRegistryItem[];
  trade: string[];
  snapshot: string[];
  liquidity: string[];
  custom: string[];
};

export type AddCustomAssetRequest = {
  symbol: string;
  label: string;
  provider: "yfinance" | "coingecko";
  ticker: string;
  kind?: string;
};

export type AddCustomAssetResponse = {
  ok: boolean;
  symbol: string;
  bars_probed: number;
};

export type AssetAnalysisTimeframe = {
  score?: number | null;
  direction?: string | null;
  rsi?: number | null;
  ema_stack?: string | null;
  atr?: number | null;
  bars_used?: number | null;
  status?: string | null;
};

export type AssetAnalysis = {
  symbol: string;
  available: boolean;
  last_price?: number | null;
  overall_score?: number | null;
  overall_direction?: string | null;
  timeframes?: Record<string, AssetAnalysisTimeframe>;
  momentum_pct?: Record<string, number | null>;
  note?: string | null;
};

export type ChartTimeframe = "15m" | "1h" | "4h" | "1d" | "1w";

export type ChartBar = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  source?: string | null;
  verified?: boolean;
};

export type TechnicalChartResponse = {
  symbol: string;
  timeframe: ChartTimeframe;
  limit?: number;
  bars_used: number;
  source?: string | null;
  last_price?: number | null;
  generated_at?: string | null;
  bars: ChartBar[];
};

export type FibonacciLevel = {
  ratio?: number | null;
  label?: string | null;
  price?: number | null;
  kind?: string | null;
  role?: string | null;
  distance_pct?: number | null;
};

export type FibonacciFrame = {
  timeframe?: string | null;
  swing_high?: number | null;
  swing_low?: number | null;
  swing_start?: string | null;
  swing_end?: string | null;
  trend_direction?: string | null;
  levels?: FibonacciLevel[];
  nearest_level?: FibonacciLevel | null;
  nearest_distance_pct?: number | null;
  zone?: string | null;
  validity?: string | null;
  diagnostics?: string[];
};

export type TechnicalInsight = {
  symbol: string;
  fib_1d?: FibonacciFrame | null;
  fib_4h?: FibonacciFrame | null;
  fib_confluence?: {
    has_confluence?: boolean;
    confluence_zone?: string | null;
    nearest_1d_level?: FibonacciLevel | null;
    nearest_4h_level?: FibonacciLevel | null;
    distance_between_levels_pct?: number | null;
    score?: number | null;
    reason?: string | null;
    diagnostics?: string[];
  } | null;
  fibonacci_score?: number | null;
};

export type ElliottWavePoint = {
  label?: string | null;
  bar_index?: number | null;
  price?: number | null;
  ts?: string | null;
};

export type ElliottAnalysis = {
  timeframe?: string | null;
  primary_scenario?: string | null;
  confidence?: number | null;
  wave_points?: ElliottWavePoint[];
  invalidation_price?: number | null;
  target_zone?: [number, number] | null;
  bias?: string | null;
  degree?: string | null;
  rules_passed?: string[];
  rules_failed?: string[];
  diagnostics?: string[];
};

export type PriceZone = {
  kind?: string | null;
  price_low?: number | null;
  price_high?: number | null;
  touches?: number | null;
  distance_pct?: number | null;
};

export type ZoneAnalysis = {
  timeframe?: string | null;
  zones?: PriceZone[];
  nearest_zone?: PriceZone | null;
  location?: string | null;
  range_high?: number | null;
  range_low?: number | null;
  validity?: string | null;
  diagnostics?: string[];
};

export type VolumeAnalysis = {
  timeframe?: string | null;
  state?: string | null;
  volume_ratio?: number | null;
  price_direction?: string | null;
  trend_direction?: string | null;
  validity?: string | null;
  diagnostics?: string[];
};

export type AnchoredVWAPLevel = {
  anchor?: string | null;
  anchor_bar_index?: number | null;
  vwap_price?: number | null;
  location?: string | null;
  distance_pct?: number | null;
};

export type VWAPAnalysis = {
  timeframe?: string | null;
  session_vwap?: number | null;
  location?: string | null;
  deviation_pct?: number | null;
  deviation_extreme?: boolean;
  reclaim?: boolean;
  rejection?: boolean;
  anchored?: AnchoredVWAPLevel[];
  validity?: string | null;
  diagnostics?: string[];
};

export type LiquiditySweepAnalysis = {
  timeframe?: string | null;
  state?: string | null;
  swing_high?: number | null;
  swing_low?: number | null;
  sweep_price?: number | null;
  reclaim_price?: number | null;
  bias?: string | null;
  validity?: string | null;
  diagnostics?: string[];
};

export type ExhaustionAnalysis = {
  timeframe?: string | null;
  score?: number | null;
  rsi?: number | null;
  recent_return_pct?: number | null;
  contributions?: string[];
  validity?: string | null;
  diagnostics?: string[];
};

export type LocationScoreAnalysis = {
  score?: number | null;
  location_class?: string | null;
  contributions?: string[];
  validity?: string | null;
  diagnostics?: string[];
};

export type TriggerAnalysis = {
  timeframe?: string | null;
  state?: string | null;
  trigger_score?: number | null;
  matched_triggers?: string[];
  validity?: string | null;
  diagnostics?: string[];
};

export type MarketSessionAsset = {
  generated_at?: string | null;
  asset_code: string;
  asset_context?: {
    relevant_markets?: Array<Record<string, unknown>>;
    any_relevant_market_open?: boolean;
    primary_market_open?: boolean;
    session_risk?: string | null;
    reason?: string | null;
    diagnostics?: string[];
  } | null;
  decision?: {
    action?: string | null;
    size_multiplier?: number | null;
    reason?: string | null;
    reason_code?: string | null;
    evidence?: string[];
    diagnostics?: string[];
  } | null;
  diagnostics?: string[];
  paper_safe?: boolean;
  no_execution?: boolean;
};

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers,
  });
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    let reason: string | null = null;
    try {
      const payload = JSON.parse(raw) as {
        reason?: unknown;
        detail?: unknown;
      };
      reason =
        typeof payload.reason === "string"
          ? payload.reason
          : typeof payload.detail === "string"
            ? payload.detail
            : payload.detail &&
                typeof payload.detail === "object" &&
                "reason" in payload.detail &&
                typeof (payload.detail as { reason?: unknown }).reason === "string"
              ? (payload.detail as { reason: string }).reason
              : null;
    } catch {
      reason = null;
    }
    if (reason?.trim()) {
      throw new Error(reason);
    }
    throw new Error(`API ${res.status} ${path}: ${raw}`);
  }
  return res.json() as Promise<T>;
}

async function fetchAudio(path: string, init?: RequestInit): Promise<Blob> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status} ${path}: ${await res.text().catch(() => "")}`);
  }
  return res.blob();
}

export const api = {
  health: () => fetchJSON<Health>("/api/v1/health"),
  systemHealth: () => fetchJSON<SystemHealth>("/api/v1/system/health"),
  regimeReport: () => fetchJSON<RegimeReport>("/api/v1/regime-report/current"),
  dashboardState: () => fetchJSON<DashboardState>("/api/v1/dashboard/state"),
  aiReport: () => fetchJSON<AIReport>("/api/v1/ai-report/current"),
  paperTradingState: () =>
    fetchJSON<PaperTradingState>("/api/v1/paper-trading/state"),
  marketSessions: () =>
    fetchJSON<MarketSessionsCurrentResponse>("/api/v1/market-sessions/current"),
  marketSessionAsset: (symbol: string) =>
    fetchJSON<MarketSessionAsset>(
      `/api/v1/market-sessions/asset/${encodeURIComponent(symbol)}`,
    ),
  marketSessionsTradeUniverse: () =>
    fetchJSON<MarketSessionsTradeUniverseResponse>(
      "/api/v1/market-sessions/trade-universe",
    ),
  agentQuorumMatrix: () =>
    fetchJSON<AgentQuorumMatrixResponse>("/api/v1/dashboard/agent-quorum-matrix"),
  assetRegistry: () => fetchJSON<AssetRegistry>("/api/v1/assets"),
  addCustomAsset: (body: AddCustomAssetRequest) =>
    fetchJSON<AddCustomAssetResponse>("/api/v1/assets/custom", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeCustomAsset: (symbol: string) =>
    fetchJSON<{ ok: boolean; symbol: string }>(
      `/api/v1/assets/custom/${encodeURIComponent(symbol)}`,
      { method: "DELETE" },
    ),
  assetAnalysis: (symbol: string) =>
    fetchJSON<AssetAnalysis>(
      `/api/v1/analysis/asset/${encodeURIComponent(symbol)}`,
    ),
  technicalInsight: (symbol: string) =>
    fetchJSON<TechnicalInsight>(
      `/api/v1/technical/insight/${encodeURIComponent(symbol)}`,
    ),
  technicalChart: (symbol: string, timeframe: ChartTimeframe = "1d", limit = 180) =>
    fetchJSON<TechnicalChartResponse>(
      `/api/v1/technical/chart/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&limit=${encodeURIComponent(String(limit))}`,
    ),
  elliottScenario: (symbol: string, timeframe = "1d") =>
    fetchJSON<ElliottAnalysis>(
      `/api/v1/technical/elliott/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  zoneAnalysis: (symbol: string, timeframe = "1d") =>
    fetchJSON<ZoneAnalysis>(
      `/api/v1/technical/zones/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  volumeAnalysis: (symbol: string, timeframe = "1d") =>
    fetchJSON<VolumeAnalysis>(
      `/api/v1/technical/volume/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  vwapAnalysis: (symbol: string, timeframe = "1d") =>
    fetchJSON<VWAPAnalysis>(
      `/api/v1/technical/vwap/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  liquiditySweepAnalysis: (symbol: string, timeframe = "1d") =>
    fetchJSON<LiquiditySweepAnalysis>(
      `/api/v1/technical/liquidity-sweep/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  exhaustionScore: (symbol: string, timeframe = "1d") =>
    fetchJSON<ExhaustionAnalysis>(
      `/api/v1/technical/exhaustion/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  locationScore: (symbol: string, timeframe = "1d") =>
    fetchJSON<LocationScoreAnalysis>(
      `/api/v1/technical/location-score/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  triggerAnalysis: (symbol: string, timeframe = "1d") =>
    fetchJSON<TriggerAnalysis>(
      `/api/v1/technical/trigger/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  paperTradingTick: () =>
    fetchJSON<TickResult>("/api/v1/paper-trading/tick", { method: "POST" }),
  closePaperPosition: (positionId: string) =>
    fetchJSON<ClosePositionResult>(
      `/api/v1/paper-trading/positions/${positionId}/close`,
      { method: "POST" },
    ),
  updatePaperPositionRiskPlan: (
    positionId: string,
    body: UpdateRiskPlanRequest,
  ) =>
    fetchJSON<UpdateRiskPlanResult>(
      `/api/v1/paper-trading/positions/${positionId}/risk-plan`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  placeOrder: (body: OrderRequest) =>
    fetchJSON<OrderResult>("/api/v1/paper-trading/positions/open", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  pendingOrders: () =>
    fetchJSON<{ orders: PendingOrder[]; total: number }>("/api/v1/paper-trading/orders"),
  cancelOrder: (orderId: string) =>
    fetchJSON<{ status: string }>(`/api/v1/paper-trading/orders/${orderId}`, {
      method: "DELETE",
    }),
  cancelAllOrders: () =>
    fetchJSON<{ status: string; count: number }>("/api/v1/paper-trading/orders", {
      method: "DELETE",
    }),
  learningSummary: () =>
    fetchJSON<LearningSummary>("/api/v1/learning/summary"),
  dataSnapshot: () => fetchJSON<DataSnapshot>("/api/v1/data/snapshot"),
  liquidityRotation: () =>
    fetchJSON<LiquidityRotation>("/api/v1/liquidity/rotation"),
  rebalanceProposal: () =>
    fetchJSON<RebalanceState>("/api/v1/learning/rebalance/proposal"),
  calibration: () =>
    fetchJSON<CalibrationState>("/api/v1/learning/calibration"),
  tfWeights: () =>
    fetchJSON<TfWeightsReport>("/api/v1/learning/tf-weights"),
  tfTargets: () =>
    fetchJSON<TfTargetsView>("/api/v1/learning/tf-targets"),
  tfTargetsApprove: () =>
    fetchJSON<TfTargetsActionResult>(
      "/api/v1/learning/tf-targets/approve",
      { method: "POST" },
    ),
  tfTargetsReject: () =>
    fetchJSON<TfTargetsActionResult>(
      "/api/v1/learning/tf-targets/reject",
      { method: "POST" },
    ),
  tfTargetsRetrain: () =>
    fetchJSON<Record<string, unknown>>(
      "/api/v1/learning/tf-targets/retrain",
      { method: "POST" },
    ),
  missedOpportunities: () =>
    fetchJSON<MissedOpportunitiesView>(
      "/api/v1/learning/missed-opportunities",
    ),
  mistakes: () => fetchJSON<MistakesState>("/api/v1/learning/mistakes"),
  riskCorrelation: () =>
    fetchJSON<CorrelationState>("/api/v1/risk/correlation"),
  riskHalts: () => fetchJSON<HaltsState>("/api/v1/risk/halts"),
  riskHaltsReset: () =>
    fetchJSON<HaltResetResult>("/api/v1/risk/halts/reset", { method: "POST" }),
  tradeTickets: () =>
    fetchJSON<TradeTicketList>("/api/v1/paper-trading/tickets"),
  notifications: (unreadOnly = false) =>
    fetchJSON<NotificationList>(
      `/api/v1/notifications?limit=50&unread_only=${unreadOnly}`,
    ),
  ackNotification: (id: string) =>
    fetchJSON<{ status: string; id: string }>(
      `/api/v1/notifications/${encodeURIComponent(id)}/ack`,
      { method: "POST" },
    ),
  ackAllNotifications: () =>
    fetchJSON<{ status: string; marked: number }>(
      "/api/v1/notifications/ack-all",
      { method: "POST" },
    ),
  decisionMatrix: () =>
    fetchJSON<DecisionMatrix>("/api/v1/decision/matrix"),
  agentMatrix: () =>
    fetchJSON<AgentMatrix>("/api/v1/technical/agent-matrix"),
  shadowComparison: () =>
    fetchJSON<ShadowComparison>("/api/v1/decision/shadow"),
  conflictGateStatus: () =>
    fetchJSON<ConflictGateStatus>("/api/v1/learning/conflict-gate-status"),
  conflictGateValidation: () =>
    fetchJSON<ConflictGateValidationReport>("/api/v1/learning/conflict-gate-validation"),
  cockpitBrief: () => fetchJSON<CockpitBrief>("/api/v1/cockpit/brief"),
  replayStatus: () => fetchJSON<ReplayStatus>("/api/v1/replay/status"),
  replayBacktest: () => fetchJSON<ReplayBacktest>("/api/v1/replay/backtest"),
  replaySnapshot: (snapshotId: string) =>
    fetchJSON<ReplaySnapshot>(
      `/api/v1/replay/${encodeURIComponent(snapshotId)}`,
    ),
  replayDecisionTrace: (snapshotId: string) =>
    fetchJSON<ReplayDecisionTrace>(
      `/api/v1/replay/${encodeURIComponent(snapshotId)}/decision-trace`,
    ),
  chat: (message: string) =>
    fetchJSON<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  agentBriefing: () => fetchJSON<AgentBriefing>("/api/v1/agent/briefing"),
  voiceSpeak: (payload: VoiceSpeakRequest) =>
    fetchAudio("/api/voice/speak", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
