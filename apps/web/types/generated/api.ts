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
  timeframe?: Timeframe;
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
  timeframe?: Timeframe;
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

export type CalibrationParams = {
  a: number;
  b: number;
  samples: number;
  fitted_at: string | null;
  status: "identity" | "fitted" | "insufficient";
};

export type CalibrationState = {
  params: CalibrationParams;
  min_required: number;
  samples_in_state: number;
  bins: CalibrationBin[];
};

export type MistakeAction = "NEUTRAL" | "AVOID" | "BOOST" | "WARNING";

export type MistakeRecord = {
  fingerprint: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  last_seen_at: string | null;
  streak_losses: number;
};

export type MistakeVerdict = {
  fingerprint: string;
  action: MistakeAction;
  reason: string;
  size_factor: number;
  evidence: string[];
};

export type MistakesState = {
  thresholds: Record<string, number>;
  records: MistakeRecord[];
  verdicts: MistakeVerdict[];
  flagged_count: number;
  total_fingerprints: number;
};

export type CorrelationSource = "computed" | "baseline" | "neutral";

export type CorrelationEntry = {
  symbol_a: string;
  symbol_b: string;
  rho: number;
  source: CorrelationSource;
  samples: number;
};

export type ClusterPosition = {
  id: string;
  symbol: string;
  side: "long" | "short";
  size_usd: number;
};

export type ExposureCluster = {
  symbols: string[];
  positions: ClusterPosition[];
  total_usd: number;
  cluster_pct: number;
  status: "OK" | "WARNING" | "BREACH";
};

export type CorrelationState = {
  threshold: number;
  max_cluster_pct: number;
  window_days: number;
  min_overlap_days: number;
  symbols: string[];
  matrix: CorrelationEntry[];
  clusters: ExposureCluster[];
  open_position_count: number;
  equity_usd: number;
  insufficient_pairs: string[];
};

export type HaltType = "DAILY_LOSS" | "MAX_DRAWDOWN";
export type HaltLevel = "KILL_SWITCH" | "RISK_REDUCE";

export type HaltEvent = {
  id: string;
  type: HaltType;
  level: HaltLevel;
  started_at: string;
  reason: string;
  evidence: string[];
  active: boolean;
  cleared_at: string | null;
  cleared_by: string | null;
};

export type HaltMetrics = {
  equity_usd: number;
  peak_equity_usd: number;
  daily_pnl_usd: number;
  daily_loss_limit_usd: number;
  daily_loss_ratio: number;
  drawdown_pct: number;
  max_drawdown_pct: number;
  drawdown_ratio: number;
};

export type HaltsState = {
  halt_active: boolean;
  active: HaltEvent[];
  timeline: HaltEvent[];
  metrics: HaltMetrics;
  reset_hint: string;
};

export type HaltResetResult = {
  cleared_count: number;
  cleared: HaltEvent[];
};

// ---------------- T0 — Timeframe contracts (panel T2/T4'te gelir) ----------------

export type Timeframe = "15m" | "1h" | "4h" | "1d" | "1w";

export type CatalystImpact = {
  catalyst_id: string;
  event_type: string;
  surprise_level?: number;
  affected_assets?: string[];
  expected_half_life_minutes?: number;
  affected_timeframes?: Timeframe[];
  timeframe_bias?: Partial<Record<Timeframe, "bullish" | "bearish" | "neutral">>;
  valid_until?: string | null;
  decay_curve?: "exponential" | "linear" | "step";
  confidence?: number;
};

export type TimeframeDecision = {
  symbol: string;
  timeframe: Timeframe;
  action: "open_long" | "open_short" | "hold" | "blocked" | "watch";
  score?: number;
  direction?: "bullish" | "bearish" | "neutral";
  confidence?: number;
  size_multiplier?: number;
  reason?: string;
};

export type DecisionMatrix = {
  generated_at: string;
  symbols: string[];
  timeframes: Timeframe[];
  cells: TimeframeDecision[];
};
