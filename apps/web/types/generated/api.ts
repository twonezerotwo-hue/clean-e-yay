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
  // P0 — haber yalnızca bağlam; sembol etkisi varsa actionable, yoksa context-only.
  actionable?: boolean;
  freshness?: "FRESH" | "RECENT" | "STALE";
};

export type EventRiskLevel = "NONE" | "WATCH" | "NO_POSITION_INCREASE";

export type Catalyst = {
  id: string;
  ts: string;
  title: string;
  importance?: "low" | "medium" | "high" | "critical";
  region?: string;
  hours_until?: number;
  days_until?: number;
  // P0 — bu olayın tetiklediği event riski seviyesi (yalnızca kısıtlayıcı).
  event_level?: EventRiskLevel;
};

export type EventRiskTrigger = {
  id: string;
  title: string;
  importance: string;
  hours_until?: number;
  days_until?: number | null;
  level: "WATCH" | "NO_POSITION_INCREASE";
};

/**
 * P0 — Olay riski özeti. YALNIZCA kısıtlayıcı: yaklaşan doğrulanmış yüksek
 * etkili takvim olayı yeni pozisyon açılışını kısar. RiskGate/DQS/KillSwitch/
 * halt gate'lerini bypass etmez, size artırmaz.
 */
export type EventRiskView = {
  level: EventRiskLevel;
  action?: "WATCH" | "NO_POSITION_INCREASE" | null;
  reason?: string;
  evidence?: string[];
  restrictive: boolean;
  triggers?: EventRiskTrigger[];
};

export type RegimeReport = {
  meta: SnapshotMeta;
  regime_label: RegimeLabel;
  layers: RegimeLayer[];
  assets: AssetSignal[];
  headlines?: NewsHeadline[];
  catalysts?: Catalyst[];
  event_risk?: EventRiskView;
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

// v2.6 — persona katmanı (narrative-only; decision path'e yazmaz).
export type PersonaSection = {
  persona: "analyst" | "risk_officer" | "macro_strategist";
  title: string;
  summary: string;
  concerns?: string[];
  evidence_used?: string[];
  missing_data?: string[];
  actionability?: string;
  what_would_change_my_mind?: string;
  source?: "llm" | "fallback";
  model?: string | null;
};

export type TimeframeSummary = {
  suspended?: boolean;
  lines?: string[];
  candidate_vs_final_diffs?: {
    symbol?: string;
    timeframe?: Timeframe;
    candidate?: string;
    final?: string;
    blocked_by?: string[];
    reason?: string;
  }[];
  blocked_by_reasons?: string[];
  paper_actions?: { symbol?: string; timeframe?: Timeframe; paper_action?: string }[];
};

export type LLMMeta = {
  mode?: "off" | "mock" | "groq";
  model?: string | null;
  source?: "llm" | "fallback" | "guard";
  fallback_reason?: string | null;
  cached?: boolean;
  tokens_used?: number;
};

export type AIReport = {
  meta: SnapshotMeta;
  verdict: "bullish" | "bearish" | "neutral" | "no_trade";
  narrative: string;
  key_signals?: string[];
  token_usage?: { input?: number; output?: number; cached?: boolean };
  // v2.6 additive
  no_actionable_decision?: boolean;
  timeframe_summary?: TimeframeSummary;
  personas?: PersonaSection[];
  llm?: LLMMeta;
};

export type ChatRequest = { message: string };

export type ChatResponse = {
  answer: string;
  refused: boolean;
  evidence_used?: string[];
  snapshot_id?: string;
  llm?: LLMMeta;
  mode?: Record<string, unknown>;
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
  // T2 — TF time-stop; dolunca TIME_STOP_EXIT. null → time-stop yok.
  valid_until?: string | null;
  // UX1 — time-stop durumu backend'de; negatif geri sayım YOK.
  time_stop_status?: "NONE" | "ACTIVE" | "EXPIRED";
  time_stop_seconds_remaining?: number | null;
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
  close_reason:
    | "SL_HIT"
    | "TP_HIT"
    | "SIGNAL_REVERSAL"
    | "RISK_REDUCE"
    | "MANUAL"
    | "TIME_STOP_EXIT"
    | "KILL_SWITCH_EXIT";
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
    timeframe?: Timeframe;
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
  // UX1 — istatistiksel anlam eşiği + yeterlilik (frontend hesap yapmaz).
  min_sample?: number;
  sample_sufficient?: boolean;
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

export type TechnicalStatus = "OK" | "DEGRADED";

// T1 — gerçek OHLCV'den hesaplanan TF teknik özeti.
// Bar yetersiz/stale ise alanlar null + status DEGRADED.
export type TechnicalTf = {
  timeframe: Timeframe;
  rsi: number | null;
  macd: number | null;
  atr: number | null;
  ema_stack: "bullish" | "bearish" | "mixed" | null;
  score: number;
  status: TechnicalStatus;
  source: string;
  bars_used: number;
  ts: string;
};

// T1 — tek mum; ts = bar açılış zamanı (UTC). resample edilen barlarda
// source = "resampled:<base_tf>".
export type OHLCVBar = {
  symbol: string;
  timeframe: Timeframe;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  source?: string;
  verified?: boolean;
};

export type DataSnapshot = {
  meta: {
    snapshot_id: string;
    generated_at: string;
    symbols: string[];
  };
  // /data/snapshot runtime'da provenance damgası döner (7 alan) — SnapshotMode değil.
  mode: ProvenanceMode;
  prices: LivePrice[];
  dqs: DqsBreakdown;
  provider_status: Record<string, ProviderStatus>;
  warnings: string[];
  technicals_by_tf?: Record<string, Partial<Record<Timeframe, TechnicalTf>>>;
  // v2.7 D2 — kripto türev zekâsı (symbol → DerivativesSnapshot). Crypto-only.
  derivatives?: Record<string, DerivativesSnapshot>;
  // v2.7 D4 — realized volatility / rejim (symbol → timeframe → snapshot).
  volatility?: Record<string, Partial<Record<Timeframe, VolatilitySnapshot>>>;
  // v2.7 D3 — options IV / skew / term structure (symbol → OptionsSnapshot).
  // Yalnızca BTC/ETH; skew_25d proxy (gerçek greeks değil).
  options?: Record<string, OptionsSnapshot>;
  // v2.7 D5 — haber → catalyst half-life zekâsı (deterministik; LLM yok).
  catalyst_impacts?: CatalystImpact[];
};

// v2.7 D2 — Crypto Derivatives Intelligence (funding / OI / squeeze proxy).
// squeeze_proxy GERÇEK liquidation değildir (is_proxy=true). Karar zincirinde
// yalnızca kısıtlayıcı; asla size artırmaz.
export type SqueezeLevel = "NONE" | "LOW" | "ELEVATED" | "HIGH";
export type FundingBias = "crowded_long" | "crowded_short" | "neutral";
export type DerivativesStatus = "OK" | "DEGRADED";

export type DerivativesSnapshot = {
  symbol: string;
  funding_rate: number | null;
  funding_annualized: number | null;
  open_interest_usd: number | null;
  oi_change_pct: number | null;
  price_momentum_pct: number | null;
  volatility_pct: number | null;
  squeeze_proxy: number;
  squeeze_level: SqueezeLevel;
  funding_bias: FundingBias;
  is_proxy: boolean;
  status: DerivativesStatus;
  source: string;
  verified: boolean;
  freshness?: "FRESH" | "RECENT" | "STALE" | null;
  dqs: number;
  ts: string;
  evidence?: string[];
  error?: string | null;
};

// Matrix banner için per-symbol özet (yalnızca status=OK).
export type DerivativesSummary = {
  symbol: string;
  squeeze_level: SqueezeLevel;
  squeeze_proxy: number;
  funding_bias: FundingBias;
  funding_rate?: number | null;
  is_proxy: boolean;
  status: DerivativesStatus;
  verified: boolean;
};

// v2.7 D4 — Realized Volatility / Volatility Regime Intelligence. Mevcut OHLCV
// cache'inden; karar zincirinde YALNIZCA kısıtlayıcı (asla size artırmaz).
export type VolatilityRegime = "LOW" | "NORMAL" | "ELEVATED" | "EXTREME";
export type VolState = "normal" | "squeeze" | "expansion" | "shock";
export type VolatilityStatus = "OK" | "DEGRADED";

export type VolatilitySnapshot = {
  symbol: string;
  timeframe: Timeframe;
  realized_vol: number | null;
  rv_short: number | null;
  rv_medium: number | null;
  rv_long: number | null;
  vol_zscore: number | null;
  regime: VolatilityRegime;
  vol_state: VolState;
  status: VolatilityStatus;
  source: string;
  verified: boolean;
  freshness?: "FRESH" | "RECENT" | "STALE" | null;
  dqs: number;
  bars_used: number;
  ts: string;
  evidence?: string[];
  error?: string | null;
};

// Matrix banner için per (symbol, timeframe) özet (yalnızca status=OK).
export type VolatilitySummary = {
  symbol: string;
  timeframe: Timeframe;
  regime: VolatilityRegime;
  vol_state: VolState;
  realized_vol?: number | null;
  vol_zscore?: number | null;
  status: VolatilityStatus;
  verified: boolean;
};

// v2.7 D3 — Options IV / Skew / Term Structure Intelligence (yalnızca BTC/ETH).
// skew_25d GERÇEK 25Δ greeks değildir (is_proxy=true). Karar zincirinde YALNIZCA
// kısıtlayıcı (asla size artırmaz; CHEAP_VOL bile yalnızca bağlam).
export type OptionsRegime =
  | "NORMAL"
  | "RICH_VOL"
  | "CHEAP_VOL"
  | "PUT_SKEW_STRESS"
  | "CALL_SKEW_EUPHORIA"
  | "TERM_STRESS";
export type OptionsStatus = "OK" | "DEGRADED" | "UNAVAILABLE";

export type OptionsSnapshot = {
  symbol: string;
  underlying_price: number | null;
  atm_iv: number | null;
  realized_vol: number | null;
  iv_rv_spread: number | null;
  skew_25d: number | null;
  put_call_oi_ratio: number | null;
  term_front_iv: number | null;
  term_next_iv: number | null;
  term_long_iv: number | null;
  term_slope: number | null;
  front_expiry: string | null;
  next_expiry: string | null;
  long_expiry: string | null;
  contracts_used: number;
  regime: OptionsRegime;
  is_proxy: boolean;
  status: OptionsStatus;
  source: string;
  verified: boolean;
  freshness?: "FRESH" | "RECENT" | "STALE" | null;
  dqs: number;
  ts: string;
  evidence?: string[];
  error?: string | null;
};

// Matrix banner için per-symbol özet (yalnızca status=OK + rejim ≠ NORMAL).
export type OptionsSummary = {
  symbol: string;
  regime: OptionsRegime;
  atm_iv?: number | null;
  realized_vol?: number | null;
  iv_rv_spread?: number | null;
  skew_25d?: number | null;
  put_call_oi_ratio?: number | null;
  term_slope?: number | null;
  front_expiry?: string | null;
  next_expiry?: string | null;
  long_expiry?: string | null;
  is_proxy: boolean;
  source: string;
  freshness?: "FRESH" | "RECENT" | "STALE" | null;
  status: OptionsStatus;
  verified: boolean;
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

// v2.7 D5 — Catalyst half-life intelligence (haber → etki modeli).
export type CatalystEventType =
  | "geopolitical_deescalation"
  | "geopolitical_escalation"
  | "inflation_data"
  | "jobs_data"
  | "central_bank"
  | "oil_supply"
  | "oil_inventory"
  | "crypto_etf_flow"
  | "funding_oi_squeeze"
  | "earnings"
  | "exchange_outage"
  | "rumor_unverified"
  | "unknown";

export type CatalystActionability =
  | "CONTEXT_ONLY"
  | "WATCH"
  | "CAUTION"
  | "NO_POSITION_INCREASE";

export type CatalystImpact = {
  catalyst_id: string;
  headline_id?: string;
  event_type: CatalystEventType;
  surprise_level?: number;
  affected_assets?: string[];
  expected_half_life_minutes?: number;
  affected_timeframes?: Timeframe[];
  timeframe_bias?: Partial<Record<Timeframe, "bullish" | "bearish" | "neutral">>;
  valid_until?: string | null;
  decay_curve?: "exponential" | "linear" | "step";
  confidence?: number;
  actionability: CatalystActionability;
  verified: boolean;
  source?: string;
  region?: string | null;
  freshness?: "FRESH" | "RECENT" | "STALE" | null;
  ts?: string;
  evidence?: string[];
};

// v2.7 D5 — DecisionMatrix banner özeti (verified + yarı-ömrü dolmamış).
export type CatalystSummary = {
  catalyst_id: string;
  headline_id?: string;
  event_type: CatalystEventType;
  actionability: CatalystActionability;
  affected_assets?: string[];
  affected_timeframes?: Timeframe[];
  expected_half_life_minutes?: number;
  valid_until?: string | null;
  surprise_level?: number;
  confidence?: number;
  verified?: boolean;
};

// Provenance damgası (LIVE / MOCK_MODE / SIMULATION / INSUFFICIENT_DATA).
export type ProvenanceMode = {
  live_data: boolean;
  mock_mode: boolean;
  mock_warning: boolean;
  test_mock: boolean;
  dqs_status: string;
  label: string;
  advisory: string;
};

// T2 — matrix hücresi: candidate (consensus niyeti) vs final (action) ayrımı,
// blocked_by + rozet backend'de hesaplanır (frontend hesap yapmaz).
export type MatrixCellStatus = "ACTIONABLE" | "NOT_ACTIONABLE" | "SUSPENDED";

export type TimeframeDecision = {
  symbol: string;
  timeframe: Timeframe;
  action: "open_long" | "open_short" | "hold" | "blocked" | "watch";
  candidate_action?: "open_long" | "open_short" | "hold" | "blocked" | "watch";
  score?: number;
  direction?: "bullish" | "bearish" | "neutral";
  confidence?: number;
  size_multiplier?: number;
  reason?: string;
  blocked_by?: string[];
  actionable?: boolean;
  status?: MatrixCellStatus;
  paper_action?: "open_long" | "open_short" | "none";
};

export type DecisionMatrix = {
  generated_at: string;
  symbols: string[];
  timeframes: Timeframe[];
  regime?: string;
  risk_gate?: { action: string; reason: string; evidence?: string[] };
  dqs_status?: DqsStatus;
  suspended?: boolean;
  event_risk?: EventRiskView;
  // v2.7 D2 — per-symbol türev özeti (banner). Etkilenen hücreler
  // blocked_by="derivatives_risk:*" + reason ile zaten görünür.
  derivatives?: DerivativesSummary[];
  // v2.7 D4 — per (symbol, timeframe) realized vol özeti (banner). Etkilenen
  // hücreler blocked_by="volatility_risk:*" ile görünür.
  volatility?: VolatilitySummary[];
  // v2.7 D5 — verified + yarı-ömrü dolmamış catalyst özeti (banner). Etkilenen
  // hücreler blocked_by="catalyst_risk:*" ile görünür.
  catalysts?: CatalystSummary[];
  // v2.7 D3 — per-symbol options özeti (banner; rejim ≠ NORMAL). Etkilenen
  // hücreler blocked_by="options_risk:*" + reason ile görünür.
  options?: OptionsSummary[];
  mode?: ProvenanceMode;
  cells: TimeframeDecision[];
};

// ---------------- R1 — gerçek snapshot replay foundation ----------------
// Replay = kaydedilmiş gerçek state'in incelenmesi. Sahte backtest / uydurma
// geçmiş performans YOK. PAPER_SAFE / NO_EXECUTION.

export type ReplayStoreStatus = "active" | "empty" | "reserved_not_active";
export type ReplayMode =
  | "active_snapshot_replay"
  | "insufficient_snapshots"
  | "reserved_not_active";
export type ReplayExecution = "no_live_execution";

export type ReplayStatus = {
  status: ReplayStoreStatus;
  available: boolean;
  mode: ReplayMode;
  snapshot_count: number;
  latest_snapshot_id?: string | null;
  latest_generated_at?: string | null;
  schema_version?: number;
  reason?: string;
  execution?: ReplayExecution;
};

export type ReplaySnapshot = {
  snapshot_id: string;
  status: "active";
  available: boolean;
  execution?: ReplayExecution;
  snapshot: Record<string, unknown>;
};

export type ReplayDecisionTrace = {
  snapshot_id: string;
  generated_at?: string | null;
  schema_version?: number;
  available: boolean;
  execution?: ReplayExecution;
  note?: string;
  mode?: Record<string, unknown> | null;
  dqs?: Record<string, unknown> | null;
  regime?: string | null;
  suspended?: boolean;
  risk_gate?: Record<string, unknown> | null;
  top_candidates: Array<Record<string, unknown>>;
  final_decisions: Array<Record<string, unknown>>;
  blocked_by_reasons?: string[];
  paper_actions?: Array<Record<string, unknown>>;
  paper_state_summary?: Record<string, unknown> | null;
  provider_issues?: Record<string, unknown>;
  deep_data?: Record<string, unknown>;
};

// ---------------- R2 — deterministic rolling backtest ----------------
// Stored snapshot serisi üzerinde outcome ölçümü. Live refetch / sahte geçmiş
// YOK; look-ahead yok. PAPER_SAFE / NO_EXECUTION.

export type ReplayBacktestStatus =
  | "ok"
  | "insufficient_snapshots"
  | "insufficient_future_data";

export type ReplayBacktestMetrics = {
  signals_evaluated: number;
  suppressed_evaluated: number;
  hits?: number;
  hit_rate?: number | null;
  false_positive?: number;
  false_positive_rate?: number | null;
  false_negative?: number;
  false_negative_rate?: number | null;
  avg_return?: number | null;
  max_drawdown?: number | null;
  blocked_decision_accuracy?: number | null;
};

export type ReplayBacktest = {
  run_id: string;
  algo_version?: number;
  status: ReplayBacktestStatus;
  available: boolean;
  execution: ReplayExecution;
  reason?: string;
  snapshot_count: number;
  usable_snapshot_count?: number;
  evaluated_snapshots?: number;
  horizons?: string[];
  window?: Record<string, unknown> | null;
  metrics: ReplayBacktestMetrics;
  per_timeframe?: Record<string, ReplayBacktestMetrics>;
  per_symbol?: Record<string, ReplayBacktestMetrics>;
  per_horizon?: Record<string, ReplayBacktestMetrics>;
  coverage?: Record<string, unknown>;
};

// ---------------- UX1 — Agent Operating Cockpit ----------------
// Tüm türetilmiş alanlar backend ViewModel'inden gelir (frontend hesap
// yapmaz). Read-only; yeni karar/emir/live çağrı YOK. PAPER_SAFE.

export type AgentStatus =
  | "ACTIONABLE"
  | "NO_ACTION"
  | "WATCHING"
  | "FROZEN"
  | "BLOCKED";

export type MainBlockerCode =
  | "DQS_BLOCKED"
  | "HALT"
  | "PROVIDER_DOWN"
  | "RISK_GATE"
  | "NONE";

export type DataMode =
  | "LIVE_VERIFIED"
  | "LIVE_DEGRADED"
  | "PARTIAL_FALLBACK"
  | "SIMULATION"
  | "BLOCKED";

export type MainBlocker = {
  code: MainBlockerCode;
  label: string;
  detail: string;
};

export type WatchCondition = {
  key: string;
  label: string;
  detail?: string;
};

export type AgentBriefCandidate = {
  symbol?: string;
  timeframe?: Timeframe;
  direction?: "bullish" | "bearish" | "neutral";
  score?: number;
  candidate_action?: string;
  final_action?: string;
  actionable?: boolean;
  status?: MatrixCellStatus;
};

export type AgentBrief = {
  status: AgentStatus;
  can_act: boolean;
  main_blocker: MainBlocker;
  summary: string;
  data_mode: DataMode;
  regime?: string | null;
  dqs?: { status?: DqsStatus | null; score?: number | null };
  risk?: { action?: string | null; reason?: string | null };
  open_paper_positions?: number;
  top_blockers?: string[];
  top_candidates?: AgentBriefCandidate[];
  next_watch_conditions?: WatchCondition[];
  recommended_stance: string;
  paper_state_summary?: {
    open_positions?: number;
    expired_time_stops?: number;
    new_entries_disabled?: boolean;
    frozen?: boolean;
    current_paper_actions?: Array<Record<string, unknown>>;
  };
  generated_at?: string;
};

export type DecisionTrace = {
  candidate_decisions: Array<Record<string, unknown>>;
  final_decisions: Array<Record<string, unknown>>;
  blocked_by: string[];
  risk_gate?: { action?: string; reason?: string; evidence?: string[] } | null;
  restrictive_gates?: string[];
  paper_action?: Array<Record<string, unknown>>;
  evidence_refs?: string[];
};

export type CockpitBrief = {
  generated_at?: string;
  mode?: ProvenanceMode;
  agent_brief: AgentBrief;
  decision_trace: DecisionTrace;
};
