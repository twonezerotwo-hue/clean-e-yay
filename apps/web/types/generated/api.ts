/**
 * Generated from contracts/openapi.yaml — DO NOT EDIT BY HAND.
 *
 * Şu an manuel olarak yazıldı (iskelet); `pnpm codegen` (openapi-typescript)
 * çalıştırıldığında dosya yenilenir. Tipler birebir OpenAPI şemasıyla aynı.
 */

export type SnapshotMeta = {
  snapshot_id: string;
  generated_at: string;
  dqs_score?: number;
  fallback_used?: boolean;
};

export type RegimeLabel = "OFFENSIVE" | "NEUTRAL" | "DEFENSIVE" | "CRISIS";
export type Direction = "bullish" | "bearish" | "neutral";
export type AssetStatus = "BLOCKING" | "PENDING" | "CONFIRMED";
export type WinRateSignal = "AVOID" | "NORMAL" | "BOOST" | "INSUFFICIENT_DATA";

export type RegimeLayer = {
  name: string;
  score: number;
  direction: Direction;
  evidence?: string[];
};

export type AssetSignal = {
  symbol: string;
  score: number;
  direction: Direction;
  status: AssetStatus;
  confluence_aligned?: boolean;
  dominant_module?: string;
  win_rate_signal?: WinRateSignal;
};

export type NewsHeadline = {
  id: string;
  source: string;
  region?: string;
  ts: string;
  title: string;
  title_tr?: string;
  sentiment?: Direction;
  asset_impact?: Record<string, number>;
};

export type Catalyst = {
  id: string;
  ts: string;
  title: string;
  importance?: "low" | "medium" | "high";
  region?: string;
};

export type RegimeReport = {
  meta: SnapshotMeta;
  regime_label: RegimeLabel;
  layers: RegimeLayer[];
  assets: AssetSignal[];
  headlines?: NewsHeadline[];
  catalysts?: Catalyst[];
};

export type RiskAction =
  | "HOLD"
  | "WATCH"
  | "HEDGE_INCREASE"
  | "NO_POSITION_INCREASE"
  | "RISK_REDUCE"
  | "KILL_SWITCH";

export type RiskGate = {
  action: RiskAction;
  reason: string;
  evidence?: string[];
};

export type AgentVote = {
  persona: "analyst" | "risk_officer" | "macro_strategist";
  direction: Direction;
  confidence: number;
  narrative?: string;
};

export type ModuleHealth = Record<
  string,
  { status: "ok" | "degraded" | "down"; last_success_at?: string; notes?: string }
>;

export type DashboardState = {
  meta: SnapshotMeta;
  risk_gate: RiskGate;
  agent_votes: AgentVote[];
  quorum_reached?: boolean;
  module_health: ModuleHealth;
  warnings?: string[];
};

export type AIReport = {
  meta: SnapshotMeta;
  verdict: "bullish" | "bearish" | "neutral" | "no_trade";
  narrative: string;
  key_signals?: string[];
  token_usage?: { input?: number; output?: number; cached?: boolean };
};

export type Position = {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  current_price?: number;
  size_usd: number;
  unrealized_pnl_usd?: number;
  sl?: number;
  tp?: number;
  opened_at: string;
};

export type Trade = {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  exit_price: number;
  pnl_usd: number;
  opened_at: string;
  closed_at: string;
  close_reason: "SL_HIT" | "TP_HIT" | "SIGNAL_REVERSAL" | "RISK_REDUCE" | "MANUAL";
  fingerprint?: string;
};

export type PaperTradingState = {
  equity_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd?: number;
  max_drawdown_pct?: number;
  sharpe_30d?: number;
  open_positions: Position[];
  recent_trades: Trade[];
};

export type TickResult = {
  tick_at: string;
  signals_processed: number;
  actions: {
    symbol: string;
    action: "open" | "close" | "hold" | "blocked";
    reason?: string;
  }[];
};

export type CalibrationBin = {
  bin_lo: number;
  bin_hi: number;
  predicted: number;
  observed: number;
  count: number;
};

export type LearningSummary = {
  total_trades: number;
  win_rate: number;
  sharpe?: number;
  sortino?: number;
  max_dd_pct?: number;
  walk_forward?: {
    train_window?: number;
    test_window?: number;
    test_sharpe?: number;
    test_win_rate?: number;
  };
  calibration: CalibrationBin[];
  module_skew?: Record<string, number>;
  weights_version?: string;
};

export type Health = {
  status: "ok" | "degraded" | "down";
  version: string;
  uptime_sec: number;
};

export type ProviderStatus = {
  status: "ok" | "degraded" | "down" | "unknown";
  last_success_at: string | null;
  last_error: string | null;
  calls: number;
  fallbacks: number;
};

export type DqsStatus = "OK" | "DEGRADED" | "BLOCKED";

export type DqsBreakdown = {
  score: number;
  status: DqsStatus;
  freshness: number;
  completeness: number;
  drift: number;
  reconciliation: number;
  decision_usage: number;
  fallback_used: boolean;
  notes: string[];
};

export type PriceStatus = "OK" | "DATA_UNAVAILABLE" | "MOCK";

export type LivePrice = {
  symbol: string;
  price: number | null;
  ts: string;
  source: string;
  verified: boolean;
  status: PriceStatus;
  error: string | null;
  fallback: boolean;
};

export type SnapshotMode = {
  mock_mode: boolean;
  mock_warning: boolean;
  test_mock: boolean;
};

export type DataSnapshot = {
  meta: {
    snapshot_id: string;
    generated_at: string;
    symbols: string[];
  };
  mode: SnapshotMode;
  prices: LivePrice[];
  dqs: DqsBreakdown;
  provider_status: Record<string, ProviderStatus>;
  warnings: string[];
};

export type WeightDelta = {
  module: string;
  old: number;
  new: number;
  delta: number;
};

export type ModulePerf = {
  module: string;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
  total_pnl: number;
  score: number;
};

export type ProposalStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED";

export type RebalanceProposalRecord = {
  status: ProposalStatus;
  from_version: string;
  to_version: string;
  generated_at: string;
  regime: string;
  deltas: WeightDelta[];
  evidence: ModulePerf[];
  proposed_yaml: Record<string, unknown>;
  audit_note: string;
  dataset_size: number;
  rejected_records: number;
  notes?: string[];
  approved_by?: string;
  reject_reason?: string;
  active_yaml?: string;
};

export type RebalanceState = {
  active_version: string;
  current: RebalanceProposalRecord | null;
  history: RebalanceProposalRecord[];
};
