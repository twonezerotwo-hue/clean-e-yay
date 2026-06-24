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
  TickResult,
  TradeTicketList,
  AgentBriefing,
  VoiceSpeakRequest,
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
    throw new Error(`API ${res.status} ${path}: ${await res.text().catch(() => "")}`);
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
  assetRegistry: () => fetchJSON<AssetRegistry>("/api/v1/assets"),
  assetAnalysis: (symbol: string) =>
    fetchJSON<AssetAnalysis>(
      `/api/v1/analysis/asset/${encodeURIComponent(symbol)}`,
    ),
  technicalInsight: (symbol: string) =>
    fetchJSON<TechnicalInsight>(
      `/api/v1/technical/insight/${encodeURIComponent(symbol)}`,
    ),
  paperTradingTick: () =>
    fetchJSON<TickResult>("/api/v1/paper-trading/tick", { method: "POST" }),
  closePaperPosition: (positionId: string) =>
    fetchJSON<ClosePositionResult>(
      `/api/v1/paper-trading/positions/${positionId}/close`,
      { method: "POST" },
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
