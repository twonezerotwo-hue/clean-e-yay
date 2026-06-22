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
  RegimeReport,
  ReplayStatus,
  ShadowComparison,
  SystemHealth,
  TfWeightsReport,
  TickResult,
  TradeTicketList,
  AgentBriefing,
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
  paperTradingTick: () =>
    fetchJSON<TickResult>("/api/v1/paper-trading/tick", { method: "POST" }),
  closePaperPosition: (positionId: string) =>
    fetchJSON<ClosePositionResult>(
      `/api/v1/paper-trading/positions/${positionId}/close`,
      { method: "POST" },
    ),
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
  chat: (message: string) =>
    fetchJSON<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  agentBriefing: () => fetchJSON<AgentBriefing>("/api/v1/agent/briefing"),
};
