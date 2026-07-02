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
  // Senaryo paneli risk-on/risk-off kovası için asset sınıfı (risk/commodity/
  // hedge/safe/cash/macro) — additive.
  kind?: string | null;
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

// Küresel Likidite Rotasyon — sabit sepet flow skoru (1D/7D/30D). Gözlemci.
export type FlowDirection = "in" | "out" | "neutral";
export type LiquidityRegime =
  | "RISK_ON"
  | "CONTROLLED_RISK_ON"
  | "NEUTRAL"
  | "RISK_OFF"
  | "CRISIS";
export type LiquidityAssetFlow = {
  symbol: string;
  label: string;
  kind: string;
  return_pct: number | null;
  volume_change_pct: number | null;
  tvl_change_pct?: number | null;
  flow_score: number;
  direction: FlowDirection;
};
export type LiquidityWindow = {
  window: "1D" | "7D" | "30D";
  assets: LiquidityAssetFlow[];
  regime: LiquidityRegime;
  regime_reasons: string[];
  contradictions: string[];
};
export type LiquidityRotation = {
  windows: LiquidityWindow[];
  basket_size: number;
};

// Agent persona quorum per-symbol across the trade universe (not pinned to
// a single symbol, unlike DashboardState.agent_votes).
export type AgentQuorumRow = {
  symbol: string;
  lead_direction: string | null;
  quorum_reached: boolean;
  tally: Record<string, number>;
};
export type AgentQuorumMatrixResponse = {
  generated_at: string;
  symbols: AgentQuorumRow[];
};

// Per-asset session gate for the whole trade universe in one call.
export type MarketSessionTradeUniverseAsset = {
  asset_code: string;
  primary_market_open: boolean | null;
  action: "allow" | "caution" | "manual_ready" | "block";
  reason: string;
};
export type MarketSessionsTradeUniverseResponse = {
  generated_at: string;
  assets: MarketSessionTradeUniverseAsset[];
  paper_safe: boolean;
  no_execution: boolean;
};

// Pilot — live technical-bias engine replayed over historical OHLCV bars.
export type StrategyBacktestTrade = {
  side: "long" | "short";
  entry_ts: string;
  entry_price: number;
  exit_ts: string;
  exit_price: number;
  exit_reason: "SL_HIT" | "TP_HIT";
  pnl_pct: number;
  bars_held: number;
};
export type StrategyBacktestResult = {
  status: "ok" | "insufficient_bars";
  symbol: string;
  timeframe: string;
  scope?: "technical_only";
  bars_used?: number;
  bars_available?: number;
  bars_required?: number;
  window?: { from: string; to: string };
  total_trades?: number;
  wins?: number;
  losses?: number;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  profit_factor?: number | null;
  trades?: StrategyBacktestTrade[];
};
export type StrategyBacktestAllResult = {
  status: "ok" | "insufficient_bars";
  timeframe: string;
  scope?: "technical_only";
  symbols_evaluated: number;
  symbols_total: number;
  total_trades: number;
  overall_win_rate: number | null;
  per_symbol: Record<string, StrategyBacktestResult>;
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
  mode?: "off" | "mock" | "groq" | "openrouter" | "ollama";
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

export type VoiceSpeakRequest = {
  text: string;
  voice?: string | null;
  provider?: string | null;
};

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
  // P1 — lifecycle state machine + learning handoff (additive).
  lifecycle_status?: PaperLifecycleStatus;
  time_stop_expired?: boolean;
  pending_exit_reason?: string | null;
  open_reason?: string | null;
  snapshot_id?: string | null;
  scale_in?: boolean;
};

// P1 — paper pozisyon yaşam döngüsü durumu (canlı + terminal).
export type PaperLifecycleStatus =
  | "OPEN"
  | "EXIT_PENDING"
  | "EXPIRED_PENDING_PRICE"
  | "CLOSED"
  | "FORCE_CLOSED"
  | "ERROR_STATE";

// P1 — paper lifecycle audit olayı (append-only JSONL); alanlar additive.
export type PaperAuditEvent = {
  event_id: string;
  timestamp: string;
  action: string;
  position_id?: string;
  symbol?: string;
  timeframe?: string;
  reason?: string;
  price_used?: number;
  size?: number;
  pnl?: number;
  snapshot_id?: string;
  [key: string]: unknown;
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
    | "TRAILING_STOP_EXIT"
    | "KILL_SWITCH_EXIT";
  fingerprint?: string;
  timeframe?: Timeframe;
  // P1 — terminal lifecycle + learning handoff (additive).
  lifecycle_status?: PaperLifecycleStatus;
  open_reason?: string | null;
  snapshot_id?: string | null;
};

export type PositionRecheckVerdict = "OK" | "WATCH" | "REDUCE" | "EXIT_RECOMMEND";

export type PositionRecheck = {
  position_id: string;
  symbol: string;
  timeframe: string;
  side: "long" | "short";
  verdict: PositionRecheckVerdict;
  reason: string;
  fresh_action?: "open_long" | "open_short" | "hold" | "blocked" | null;
  fresh_direction?: Direction | null;
  fresh_confidence?: number | null;
  pnl_pct: number;
  checked_at: string;
};

export type PaperTradingState = {
  equity_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd?: number;
  max_drawdown_pct?: number;
  sharpe_30d?: number;
  open_positions: Position[];
  recent_trades: Trade[];
  // P1 — additive lifecycle/audit yüzeyi.
  new_entries_disabled?: boolean;
  duplicate_warning?: Array<Record<string, unknown>>;
  audit_summary?: Record<string, unknown>;
  recent_audit_events?: PaperAuditEvent[];
  // P2 — owner onayı bekleyen aday sayısı (queue listesi ayrı endpoint'ten gelir).
  manual_ready_count?: number;
  // UX-A14 — açık pozisyonların fresh karara karşı verdict'i (read-only).
  position_rechecks?: PositionRecheck[];
  last_recheck_at?: string | null;
  // Portföy sağlığı (ExecutionReadinessPanel) — additive.
  total_exposure_usd?: number;
  state_anomaly?: { detected: boolean; reasons: string[] };
};

// UX-A15 — Trade Ticket (broker handoff payload).
export type TradeTicketStatus = "active" | "insufficient_rr" | "invalid";

export type TradeTicketSummary = {
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  rr_ratio: number;
  rr_source: string;     // resistance | support | atr_floor | atr_max | below_floor
  size_usd: number;
  size_pct_equity: number;
  risk_usd: number;
  risk_pct_equity: number;
  confidence_calibrated: number;
  confidence_raw: number;
  confidence_label: string;  // "yüksek" / "orta" / vb.
  consensus_score: number;
  consensus_direction: Direction;
  atr: number;
};

export type TradeTicketDisplay = {
  title: string;
  expiry_text: string;
  rr_text: string;
  rr_note: string;
  why_bullets: string[];
  safety_lines: { level: "ok" | "warn" | "error"; text: string }[];
  confidence_text: string;
};

export type TradeTicket = {
  id: string;
  symbol: string;
  side: "long" | "short" | string;
  timeframe: string;
  status: TradeTicketStatus;
  expires_at: string;
  ttl_seconds: number;
  summary: TradeTicketSummary;
  technical_detail: Record<string, unknown>;  // 7 bölüm derin veri
  display: TradeTicketDisplay;
};

export type TradeTicketList = {
  tickets: TradeTicket[];
  total: number;
  last_built_at?: string | null;
};

// UX-A16 — Notifications (observer; karar vermez).
export type NotificationType =
  | "ticket_created"
  | "ticket_expiring"
  | "ticket_expired"
  | "ticket_blocked"
  | "recheck_exit_recommend"
  | "recheck_reduce"
  | "risk_gate_changed"
  | "risk_kill_switch"
  | "catalyst_imminent"
  | "dqs_dropped"
  | "position_near_sl"
  | "position_near_tp";

export type NotificationPriority = "critical" | "high" | "medium" | "low";

export type Notification = {
  id: string;
  ts: string;
  type: NotificationType;
  priority: NotificationPriority;
  title: string;
  body_short: string;
  body_long: string;
  ticket_id?: string | null;
  position_id?: string | null;
  actions?: { label: string; deep_link?: string }[];
  ack: boolean;
};

export type NotificationList = {
  notifications: Notification[];
  unread_count: number;
  total: number;
};

// P2 — owner-approval (manual-ready) workflow.
export type ManualReadyTrade = {
  id: string;
  symbol: string;
  timeframe: string;
  side: string; // long | short
  requested_at: string;
  size_multiplier: number;
  requested_price?: number;
  reason?: string;
  fingerprint?: string;
  snapshot_id?: string;
  rejected_at?: string;
};

export type ManualReadyQueue = {
  manual_ready: ManualReadyTrade[];
  rejected_count: number;
};

export type ManualReadyActionResult = {
  status: string; // opened | not_found | no_price | blocked | dismissed | rejected
  position_id?: string;
  price?: number;
  reason?: string;
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
  // L1 — timeframe-aware outcome breakdown'lar (additive; backend türetir).
  outcomes_total?: number;
  verified_outcomes?: number;
  by_timeframe?: Record<string, OutcomeBucket>;
  by_symbol?: Record<string, OutcomeBucket>;
  by_regime?: Record<string, OutcomeBucket>;
  by_dominant_module?: Record<string, OutcomeBucket>;
  by_close_reason?: Record<string, OutcomeBucket>;
  worker_last_run?: LearningWorkerRun | null;
  proposal_status?: string;
};

export type OutcomeBucket = {
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  verified: number;
};

export type LearningWorkerRun = {
  run_id: string;
  started_at: string;
  completed_at: string;
  status: string;
  skipped_reason?: string | null;
  outcomes_seen: number;
  proposals_generated: number;
  calibration_status: string;
  errors: string[];
};

export type Health = {
  status: "ok" | "degraded" | "down";
  version: string;
  uptime_sec: number;
};

// O1 — worker reliability / system health.
export type WorkerHealth = {
  worker_name: string;
  // RUNNING | OK | DEGRADED | FAILED | NO_DATA | STALE | UNKNOWN
  status: string;
  stale: boolean;
  run_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  age_seconds?: number | null;
  cycle_count: number;
  snapshots_written: number;
  decisions_generated: number;
  paper_actions: number;
  learning_outcomes_seen: number;
  proposals_generated: number;
  duration_ms?: number | null;
};

export type SystemHealth = {
  api_status: string;
  paper_safe: boolean;
  no_execution: boolean;
  workers: {
    tick_worker?: WorkerHealth;
    learning_worker?: WorkerHealth;
  };
  stale_workers?: string[];
  last_successful_tick?: string | null;
  last_learning_run?: string | null;
  provider_summary?: {
    providers?: Record<string, number>;
    degraded_count?: number;
    total?: number;
  };
  dqs_status?: string | null;
  snapshot_store_status?: Record<string, unknown>;
  risk_halt_status?: {
    active?: boolean;
    count?: number;
    types?: string[];
  };
  warnings?: string[];
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
  // Layer0HumanComputerModel'in 3D nabız animasyon hızı için backend-türetilmiş
  // sunum değeri (0-1) — karar/risk hesabına girmez.
  stress_score?: number;
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

// SnapshotMode (mock_mode/mock_warning/test_mock) was a dead friendly type — never
// referenced; /data/snapshot + /dashboard/state return the 7-field ProvenanceMode
// provenance stamp instead. Removed in Phase 3 (no schema invented for a non-response).

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
  | "REJECTED"
  | "AUTO_APPLIED";

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

// G3 — otomatik-uygulanan ağırlık değişikliği kaydı (izleme + ledger).
export type WeightAutoApplyEntry = {
  event?: "AUTO_APPLIED" | "CONFIRMED" | "ROLLED_BACK";
  status?: "MONITORING" | "CONFIRMED" | "ROLLED_BACK";
  applied_version?: string;
  prev_version?: string;
  regime?: string | null;
  baseline_expectancy?: number;
  baseline_n?: number;
  post_expectancy?: number;
  post_n?: number;
  applied_at?: string;
  resolved_at?: string;
};

export type WeightAutoApplyState = {
  active: WeightAutoApplyEntry | null;
  ledger: WeightAutoApplyEntry[];
};

export type RebalanceState = {
  active_version: string;
  current: RebalanceProposalRecord | null;
  history: RebalanceProposalRecord[];
  auto_apply?: WeightAutoApplyState;
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

// ── Step 8 — per-TF calibration + trust-gated tf_weights proposal (read-only) ──
export type TfCalibrationRow = {
  timeframe: string;
  strategy: string;
  trades: number;
  win_rate: number;
  expectancy?: number;
  trust: "PRIOR" | "CALIBRATED";
};

export type TfWeightDeltaRow = {
  strategy: string;
  timeframe: string;
  old: number;
  new: number;
  delta: number;
};

export type TfWeightsReport = {
  tf_weights_trusted: boolean;
  min_trades_per_tf?: number | null;
  calibrated_timeframes?: string[];
  per_timeframe: TfCalibrationRow[];
  proposal_status: string;
  deltas: TfWeightDeltaRow[];
  note?: string;
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

// F2-2: computed_price = gerçek 1d fiyat getirisinden (flag açıkken aktif)
export type CorrelationSource = "computed_price" | "computed" | "baseline" | "neutral";

export type CorrelationEntry = {
  symbol_a: string;
  symbol_b: string;
  rho: number;
  source: CorrelationSource;
  samples: number;
  // F2-2 salt-gözlem alanları — fiyat-rho flag kapalıyken de hesaplanır
  rho_price?: number | null;
  price_samples?: number;
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
  // F2-2 — fiyat-getirisi korelasyon flag durumu + aktiflik eşiği
  price_returns_enabled?: boolean;
  price_min_overlap_days?: number;
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

// ── Market sessions (read-only, paper-safe) — backend owns session meaning ────
export type SessionPhase =
  | "closed"
  | "pre_open"
  | "opening_window"
  | "mid_session"
  | "closing_window"
  | "after_close"
  | "unknown";
export type LiquidityTone = "high" | "normal" | "thin" | "closed" | "unknown";
export type SessionRisk =
  | "normal"
  | "caution"
  | "manual_review"
  | "block"
  | "unknown";
export type SessionAction = "allow" | "caution" | "manual_ready" | "block";

export type MarketSessionStatusView = {
  market_id: string;
  label: string;
  exchange: string;
  timezone: string;
  is_open: boolean;
  is_holiday?: boolean | null;
  open_time_utc?: string | null;
  close_time_utc?: string | null;
  minutes_to_open?: number | null;
  minutes_to_close?: number | null;
  session_phase: SessionPhase;
  liquidity_tone: LiquidityTone;
  volatility_window: boolean;
  holiday_verified: boolean;
  diagnostics: string[];
};

export type AssetSessionContextView = {
  asset_code: string;
  relevant_markets: MarketSessionStatusView[];
  any_relevant_market_open: boolean;
  primary_market_open?: boolean | null;
  session_risk: SessionRisk;
  reason: string;
  diagnostics: string[];
};

export type MarketSessionDecisionView = {
  action: SessionAction;
  size_multiplier: number;
  reason: string;
  reason_code?: string | null;
  evidence: string[];
  diagnostics: string[];
};

export type MarketSessionsCurrentResponse = {
  generated_at: string;
  markets: MarketSessionStatusView[];
  diagnostics: string[];
  paper_safe: boolean;
  no_execution: boolean;
};

export type MarketSessionAssetResponse = {
  generated_at: string;
  asset_code: string;
  asset_context: AssetSessionContextView;
  decision: MarketSessionDecisionView;
  diagnostics: string[];
  paper_safe: boolean;
  no_execution: boolean;
};

// ── F1 — Multi-timeframe Fibonacci (technical evidence; backend-computed) ─────
export type FibKind = "retracement" | "extension";
export type FibRole = "support" | "resistance" | "neutral" | "unknown";
export type FibTrend = "uptrend" | "downtrend" | "range" | "unknown";
export type FibZone =
  | "near_support"
  | "near_resistance"
  | "breakout"
  | "breakdown"
  | "mid_range"
  | "unknown";
export type FibValidity = "sane" | "weak" | "unavailable";
export type FibConfluenceZone =
  | "support"
  | "resistance"
  | "mixed"
  | "none"
  | "unknown";
export type FibTF = "1D" | "4H";

export type FibonacciLevel = {
  ratio: number;
  label: string;
  price: number;
  kind: FibKind;
  role?: FibRole;
  distance_pct?: number | null;
};

export type FibonacciAnalysis = {
  timeframe: FibTF;
  swing_high?: number | null;
  swing_low?: number | null;
  swing_start?: string | null;
  swing_end?: string | null;
  trend_direction: FibTrend;
  levels: FibonacciLevel[];
  nearest_level?: FibonacciLevel | null;
  nearest_distance_pct?: number | null;
  zone: FibZone;
  validity: FibValidity;
  diagnostics: string[];
};

export type FibonacciConfluence = {
  has_confluence: boolean;
  confluence_zone: FibConfluenceZone;
  nearest_1d_level?: FibonacciLevel | null;
  nearest_4h_level?: FibonacciLevel | null;
  distance_between_levels_pct?: number | null;
  score: number;
  reason: string;
  diagnostics: string[];
};

export type TechnicalInsight = {
  symbol: string;
  fib_1d?: FibonacciAnalysis | null;
  fib_4h?: FibonacciAnalysis | null;
  fib_confluence?: FibonacciConfluence | null;
  fibonacci_score: number;
};

// ── T-MTF — Per-timeframe technical result (multi-TF feature; backend-computed) ─
// EVIDENCE only: never opens trades, never a single aggregated score
// (direction/strength stay separate). The frontend renders, never calculates.
export type IndicatorQuality = "OK" | "INSUFFICIENT_HISTORY";
export type TechnicalBias = "BULLISH" | "BEARISH" | "NEUTRAL";
export type TfVolatilityRegime =
  | "TRENDING"
  | "RANGING"
  | "SQUEEZE"
  | "EXPANSION"
  | "UNKNOWN";
export type TrendStrengthLabel = "TRENDING" | "WEAK" | "UNKNOWN";
export type TechnicalStance = "ALLOW" | "CAUTION" | "ABSTAIN" | "DEGRADED";
// `Timeframe` is declared once under "T0 — Timeframe contracts" above; reuse it.

export type IndicatorQualityReport = {
  rsi?: IndicatorQuality;
  macd?: IndicatorQuality;
  ema200?: IndicatorQuality;
  atr?: IndicatorQuality;
  adx?: IndicatorQuality;
};

export type TechnicalDataQuality = {
  status?: "OK" | "DEGRADED";
  bars_used?: number;
  stale?: boolean;
  indicator_quality?: IndicatorQualityReport;
  warnings?: string[];
};

export type TechnicalScoreOverview = {
  direction_score?: number | null;
  strength_score?: number | null;
};

export type TechnicalKeyLevels = {
  support?: number | null;
  resistance?: number | null;
  atr?: number | null;
  atr_percent?: number | null;
  stop_reference?: number | null;
  target_reference?: number | null;
};

export type TechnicalTrendStrength = {
  adx?: number | null;
  plus_di?: number | null;
  minus_di?: number | null;
  is_trending?: boolean;
  label?: TrendStrengthLabel;
};

export type TechnicalConfluenceZone = {
  price: number;
  kind: "support" | "resistance";
  components?: string[];
};

export type ConfirmationSignal = {
  name: string;
  fired?: boolean;
  detail?: string;
};

export type TechnicalTimeframeSummary = {
  bias?: TechnicalBias;
  evidence?: string[];
  warnings?: string[];
};

// ── §4.5 reversal + chart-pattern layers (EVIDENCE only, from real bars) ──────
export type ReversalType =
  | "rsi_bullish_divergence"
  | "rsi_bearish_divergence"
  | "macd_bullish_divergence"
  | "macd_bearish_divergence"
  | "double_bottom"
  | "double_top";

export type ReversalSignal = {
  type: ReversalType;
  detected: boolean;
  detail?: string;
};

export type TechnicalReversalSignals = {
  signals?: ReversalSignal[];
  bias?: TechnicalBias;
};

export type ChartPatternName =
  | "uptrend_structure"
  | "downtrend_structure"
  | "ranging";

export type ChartPattern = {
  name: ChartPatternName;
  detail?: string;
};

export type TechnicalChartPatterns = {
  active_patterns?: ChartPattern[];
  bias?: TechnicalBias;
};

export type TechnicalTimeframeResult = {
  symbol: string;
  timeframe: Timeframe;
  data_quality?: TechnicalDataQuality;
  score_overview?: TechnicalScoreOverview;
  key_levels?: TechnicalKeyLevels;
  confirmation_signals?: ConfirmationSignal[];
  trend_strength?: TechnicalTrendStrength;
  volatility_regime?: TfVolatilityRegime;
  confluence_zones?: TechnicalConfluenceZone[];
  timeframe_summary?: TechnicalTimeframeSummary;
  fibonacci_analysis?: FibonacciAnalysis | null;
  reversal_signals?: TechnicalReversalSignals | null;
  chart_pattern_analysis?: TechnicalChartPatterns | null;
  status?: "OK" | "DEGRADED";
  source?: string;
  ts?: string;
};

// ── T2 — TechnicalAgent output (one structured opinion per symbol) ────────────
export type TechnicalInvalidation = {
  timeframe?: Timeframe | null;
  price?: number | null;
  reason?: string;
};

export type TechnicalAgentOutput = {
  agent: "technical";
  symbol: string;
  per_timeframe?: { [key: string]: TechnicalTimeframeResult };
  stance?: TechnicalStance;
  direction_score?: number | null;
  strength_score?: number | null;
  used_observations?: string[];
  invalidation?: TechnicalInvalidation | null;
  missing_data?: string[];
  ts?: string;
};

// ── T2 — Cross-timeframe consensus snapshot (TF + agent aggregation) ──────────
export type AlignmentStatus =
  | "ALIGNED"
  | "PARTIAL"
  | "COUNTERTREND"
  | "CONFLICTED";

export type CrossTimeframeConfluenceZone = {
  price: number;
  kind: "support" | "resistance";
  timeframes?: string[];
  components?: string[];
};

export type ConsensusSnapshot = {
  asset: string;
  per_timeframe_bias?: { [key: string]: TechnicalBias };
  alignment_status?: AlignmentStatus;
  alignment_score?: number;
  cross_timeframe_confluence?: CrossTimeframeConfluenceZone[];
  direction_score?: number | null;
  strength_score?: number | null;
  agreement_score?: number;
  is_countertrend?: boolean;
  confirmed_count?: number;
  pending_count?: number;
  blocking_count?: number;
  evidence?: string[];
  ts?: string;
};

// ── T2 — AgentDecision (deterministic action; RiskGate stays final) ───────────
export type DecisionAction =
  | "NO_TRADE"
  | "WATCH"
  | "SCOUT_ALLOWED"
  | "CONFIRMATION_REQUIRED"
  | "RISK_REDUCE"
  | "KILL_SWITCH";

export type AgentDecision = {
  asset: string;
  action: DecisionAction;
  entry_timeframe?: Timeframe | null;
  size_multiplier?: number;
  confidence?: number;
  reason?: string;
  supporting_agents?: string[];
  blocking_agents?: string[];
  required_confirmations?: string[];
  manual_ready_required?: boolean;
  risk_gate_required?: boolean;
  ts?: string;
};

// ── T2 step 6 — per-trade cost + R:R gate output (RiskGate-side overlay) ──────
export type TradeEconomics = {
  allow: boolean;
  reason:
    | "ok"
    | "bad_rr"
    | "below_cost"
    | "insufficient_levels"
    | "invalid_entry"
    | "invalid_stop";
  rr?: number | null;
  reward_bps?: number | null;
  risk_bps?: number | null;
  cost_bps?: number;
  net_edge_bps?: number | null;
  evidence?: string[];
};

// ── T2 step 7 — composed per-symbol agent pipeline row + matrix ───────────────
// Per-TF gated direction + location-gate diagnostic (visibility for the matrix).
export type AgentTimeframeCell = {
  timeframe: Timeframe;
  direction_score?: number | null;
  strength_score?: number | null;
  bias: TechnicalBias;
  location_gate?: number | null;
};

export type AgentMatrixRow = {
  symbol: string;
  stance: TechnicalStance;
  consensus: ConsensusSnapshot;
  decision: AgentDecision;
  economics?: TradeEconomics | null;
  reversal_bias?: TechnicalBias | null;
  pattern?: string | null;
  per_timeframe?: AgentTimeframeCell[];
};

export type AgentMatrix = {
  risk_action?: string | null;
  timeframes: Timeframe[];
  symbols: AgentMatrixRow[];
};

// ── T2 step 9 — controlled activation: live-vs-shadow comparison (observe-only) ──
export type ShadowAgreement =
  | "AGREE_ENTRY"
  | "AGREE_FLAT"
  | "DISAGREE_DIRECTION"
  | "LIVE_ONLY_ENTRY"
  | "SHADOW_ONLY_ENTRY";

export type ShadowTfCalibration = {
  timeframe: string;
  strategy: string;
  trades: number;
  win_rate: number;
  trust: "PRIOR" | "CALIBRATED";
};

export type ShadowCalibration = {
  tf_weights_trusted: boolean;
  calibrated_timeframes: string[];
  min_trades_per_tf?: number | null;
  per_timeframe: ShadowTfCalibration[];
};

export type ShadowAgreementSummary = {
  agree_entry: number;
  agree_flat: number;
  disagree_direction: number;
  live_only_entry: number;
  shadow_only_entry: number;
};

export type ShadowRow = {
  symbol: string;
  agreement: ShadowAgreement;
  live_wants_entry: boolean;
  live_action?: string | null;
  live_direction?: string | null;
  live_timeframe?: string | null;
  shadow_wants_entry: boolean;
  shadow_action?: string | null;
  shadow_direction?: string | null;
  shadow_entry_timeframe?: string | null;
  shadow_stance?: string | null;
  elliott_scenario?: string | null;
  elliott_confidence?: number | null;
  elliott_bias?: string | null;
  historical_edge_sample_count?: number | null;
  historical_edge_win_rate?: number | null;
  historical_edge_confidence?: string | null;
};

export type ShadowComparison = {
  available: boolean;
  recorded_at?: string | null;
  snapshot_id?: string | null;
  risk_action?: string | null;
  affect_decision: boolean;
  affected_paper: boolean;
  summary: ShadowAgreementSummary;
  calibration: ShadowCalibration;
  rows: ShadowRow[];
};

// Faz 8/9A — Conflict Gate (packages/decision/conflict_gate.py + conflict_gate_backtest.py)
export type ConflictGateMode = "OFF" | "SOFT" | "SOFT_PLUS" | "HARD" | "HARD_MANUAL";

export type ConflictGateStatus = {
  enabled: boolean;
  profile_modes: Record<string, ConflictGateMode>;
};

export type ConflictGateRouteStats = {
  n: number;
  win_rate: number;
  avg_pnl: number;
};

export type ConflictGateValidationReport = {
  [profile: string]: Record<string, ConflictGateRouteStats> | number;
};

// Faz B — TF-aware SL/TP learning (packages/learning/tf_target_*.py)
export type TfTargetParams = {
  sl_atr_mult: number;
  rr: number;
  sl_pct_floor: number;
  sl_pct_cap: number;
};

export type TfTargetGuardrailBand = {
  min: number;
  max: number;
};

// CP4 slice 2 — edge-gate + outcome-rollback durumu.
export type TfTargetEdgeGate = {
  enabled: boolean;
  safe_to_autotune: boolean;
  active_monitor: Record<string, unknown> | null;
  rollback_history: Array<Record<string, unknown>>;
};

// CP4 slice 3 — öğrenilen per-TF trailing çarpanı.
export type TfTargetTrailAutotune = {
  enabled: boolean;
  guardrail: { min: number; max: number };
  per_timeframe: Record<string, number>;
};

export type TfTargetsView = {
  enabled: boolean;
  auto_apply_band_pct: number;
  guardrail: Record<string, TfTargetGuardrailBand>;
  effective: Record<string, TfTargetParams>;
  store_current: Record<string, TfTargetParams>;
  pending: Record<string, unknown> | null;
  history: Array<Record<string, unknown>>;
  edge_gate: TfTargetEdgeGate;
  trail_autotune: TfTargetTrailAutotune;
};

export type TfTargetsActionResult = {
  approved?: boolean;
  rejected?: boolean;
  record: Record<string, unknown> | null;
};

export type MissedOpportunityOutcomes = {
  missed_win: number;
  avoided_loss: number;
  expired: number;
};

export type MissedOpportunityActive = {
  symbol: string;
  timeframe: string;
  side: string;
  trade_profile?: string | null;
  setup_type?: string | null;
  entry?: number | null;
  sl?: number | null;
  tp?: number | null;
  opened_at?: string | null;
};

export type AgentModeConfigValues = {
  enabled_trade_profiles: string[];
  disabled_trade_profiles: string[];
  focus_mode?: string | null;
  allow_counter_context_trades: boolean;
  allow_reversal_trades: boolean;
  allow_trend_follow_trades: boolean;
  allow_range_trades: boolean;
  allow_breakout_trades: boolean;
  watch_disabled_profiles: boolean;
  close_disabled_profile_positions: boolean;
  close_requires_riskgate_pass: boolean;
};

export type AgentModeConfigView = {
  trade_profiles: string[];
  config: AgentModeConfigValues;
  overrides: Record<string, unknown>;
  applies_to: string;
};

export type AgentModeConfigUpdate = Partial<AgentModeConfigValues>;

export type MissedOpportunitiesView = {
  available: boolean;
  enabled?: boolean;
  outcomes: MissedOpportunityOutcomes;
  by_profile: Record<string, MissedOpportunityOutcomes>;
  active: MissedOpportunityActive[];
  recent: Array<Record<string, unknown>>;
};

export type BookAuditSeverity = "CRITICAL" | "WARNING" | "INFO";

export type BookAuditLesson = {
  code: string;
  severity: BookAuditSeverity;
  title: string;
  detail: string;
  symbols: string[];
  evidence: string[];
  suggested_action: string;
};

export type BookAuditView = {
  open_positions: number;
  book_total_usd: number;
  counts: Record<string, number>;
  clean: boolean;
  lessons: BookAuditLesson[];
  thresholds: Record<string, number>;
};

export type DatasetHealthLearner = {
  name: string;
  have: number;
  need: number;
  ready: boolean;
};

export type DatasetHealthView = {
  total: number;
  verified: number;
  trainable: number;
  coverage: {
    verified_pct: number;
    confidence_pct: number;
    excursion_pct: number;
  };
  learners: DatasetHealthLearner[];
  all_ready: boolean;
};

export type EdgeStabilitySegment = {
  n: number;
  win_rate: number;
  expectancy: number;
};

export type EdgeStability = {
  ready: boolean;
  reason?: string;
  have?: number;
  need?: number;
  folds?: number;
  segments: EdgeStabilitySegment[];
  win_rate_std?: number;
  positive_folds?: number;
  stable?: boolean;
};

export type EdgeReportView = {
  total: number;
  verdict: "STABLE" | "UNSTABLE" | "INSUFFICIENT";
  stability: EdgeStability;
  counterfactual: { missed_win: number; avoided_loss: number; expired: number };
  safe_to_autotune: boolean;
  // CP4-fix #2 — outlier-direnç teşhisi.
  outlier_concentration?: number;
  outlier_dependent?: boolean;
  max_outlier_concentration?: number;
  regime_coverage?: number;
};

// CP4 (final) — otonom eşik trainer durumu (threshold_trainer.status_viewmodel).
export type ThresholdOverrideEntry = {
  value: number;
  prev?: number | null;
  at?: string | null;
};

export type ThresholdMonitorEntry = {
  path: string;
  from?: number;
  to?: number;
  backtest_gain?: number;
  baseline_expectancy?: number;
  baseline_n?: number;
  applied_at?: string;
  status?: string;
  // resolved/history alanları (event, post_expectancy, post_n, resolved_at, reason)
  event?: string;
  post_expectancy?: number;
  post_n?: number;
  resolved_at?: string;
  reason?: string;
};

export type ThresholdAutotuneView = {
  enabled: boolean;
  safe_to_autotune: boolean;
  tunable: string[];
  active_overrides: Record<string, ThresholdOverrideEntry>;
  monitor?: ThresholdMonitorEntry | null;
  history: ThresholdMonitorEntry[];
};

// CP4 — eşik A/B parametre-taraması (threshold_ab.sweep, on-demand backtest).
export type ThresholdAbMetrics = {
  status?: string;
  total_trades?: number | null;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  profit_factor?: number | null;
};

export type ThresholdAbRun = ThresholdAbMetrics & { value: number };

export type ThresholdAbView = {
  param_path: string;
  symbol?: string | null;
  symbols: string[];
  timeframe: string;
  baseline_value?: number | null;
  baseline: ThresholdAbMetrics;
  runs: ThresholdAbRun[];
  best?: ThresholdAbRun | null;
  recommendation?: ThresholdAbRun | null;
  error?: string;
};

// CP4 (slice 1) — giriş/çıkış kalitesi öğrenicisi (entry_exit_quality.report).
export type EntryExitVerdict = {
  code: "EXIT_EARLY" | "STOP_TOO_TIGHT" | "ENTER_EARLY";
  detail: string;
  nudge: { dimension: string; direction: string };
};

export type EntryExitBucketMetrics = {
  n: number;
  n_usable: number;
  n_winners: number;
  n_sl_hit: number;
  sl_hit_rate: number;
  avg_capture_ratio: number | null;
  avg_give_back_pct: number | null;
  avg_winner_mfe_pct: number | null;
  avg_sl_adverse_pct: number | null;
  avg_winner_adverse_ratio: number | null;
};

export type EntryExitBucket = {
  module: string;
  timeframe: string;
  metrics: EntryExitBucketMetrics;
  verdicts: EntryExitVerdict[];
};

export type EntryExitQualityView = {
  total: number;
  usable: number;
  min_bucket: number;
  verdict_counts: Record<string, number>;
  flagged_count: number;
  buckets: EntryExitBucket[];
  thresholds: {
    capture_low: number;
    give_back_high_pct: number;
    sl_rate_high: number;
    adverse_ratio_high: number;
  };
};

// CP3 — yön güvenlik kasası (guard_safety.report).
export type GuardSafetyMonitor = {
  enabled_at?: string | null;
  mode: "transition" | "adopted";
  baseline_expectancy: number;
  baseline_n: number;
  post_expectancy: number;
  post_n: number;
  need: number;
};

export type GuardSafetyGuard = {
  guard_key: string;
  label: string;
  config_enabled: boolean;
  vault_disabled: boolean;
  effective_enabled: boolean;
  monitoring: boolean;
  monitor?: GuardSafetyMonitor | null;
  override?: { reason?: string; by?: string; at?: string } | null;
};

export type GuardSafetyView = {
  available: boolean;
  auto_disable_enabled: boolean;
  min_outcomes: number;
  monitor_max_age_hours: number;
  guards: GuardSafetyGuard[];
  history: Array<Record<string, unknown>>;
};

export type CalibrationGuardrailStatus = {
  enabled: boolean;
  max_inflation_delta: number;
};

export type CalibrationJumpRow = {
  ts?: string | null;
  position_id?: string | null;
  symbol?: string | null;
  timeframe?: string | null;
  side?: string | null;
  raw_confidence?: number | null;
  fitted_confidence?: number | null;
  inflation_delta?: number | null;
  confidence_source?: string | null;
  platt_a?: number | null;
  platt_b?: number | null;
  platt_status?: string | null;
  platt_samples?: number | null;
  score?: number | null;
  dominant_module?: string | null;
  direction?: string | null;
  confluence_aligned?: boolean | null;
  regime?: string | null;
  tier?: string | null;
  size_usd?: number | null;
  fingerprint?: string | null;
};

export type CalibrationJumpsView = {
  guardrail: CalibrationGuardrailStatus;
  count: number;
  fitted_count: number;
  capped_count: number;
  avg_inflation_delta?: number | null;
  max_inflation_delta?: number | null;
  by_tier: Record<string, number>;
  by_dominant_module: Record<string, number>;
  top_jumps: CalibrationJumpRow[];
  recent: CalibrationJumpRow[];
};

export type AgentBriefingTone = "ok" | "info" | "warn" | "alert";

export type AgentBriefingHeadline = {
  tone: AgentBriefingTone;
  category: string;
  title: string;
  detail?: string | null;
};

export type AgentBriefingStance =
  | "halt"
  | "stale"
  | "blocked"
  | "data_gap"
  | "signal"
  | "watching"
  | "calm";

export type AgentBriefingExecutive = {
  stance: AgentBriefingStance;
  stance_label: string;
  tone: AgentBriefingTone;
  headline: string;
  narrative: string;
  recommendation: string;
  flags: string[];
};

export type AgentBriefingEngine = {
  status: string;
  age_seconds?: number | null;
  cycle_count: number;
  stale: boolean;
};

export type AgentBriefingDqs = {
  score: number;
  status: string;
};

export type AgentBriefing = {
  generated_at: string;
  snapshot_id?: string | null;
  regime_label?: string | null;
  stale?: boolean;
  executive?: AgentBriefingExecutive;
  engine?: AgentBriefingEngine;
  dqs?: AgentBriefingDqs;
  headlines: AgentBriefingHeadline[];
};

// ── Governor (self-managing katman) ─────────────────────────────────────────

export type GovernorProposalType =
  | "WEIGHT_CHANGE"
  | "MODE_CHANGE"
  | "THRESHOLD_CHANGE"
  | "RISK_POLICY_CHANGE"
  | "DATA_PROVIDER_CHANGE"
  | "TF_TARGET_CHANGE"
  | "STRATEGY_ENABLE"
  | "STRATEGY_DISABLE"
  | "DASHBOARD_ALERT";

export type GovernorProposalStatus = "PENDING" | "APPROVED" | "REJECTED";

export type GovernorProposal = {
  proposal_id: string;
  proposal_type: GovernorProposalType;
  status: GovernorProposalStatus;
  title: string;
  summary?: string;
  evidence?: Record<string, unknown>;
  requested_change?: Record<string, unknown>;
  rollback_plan?: string;
  source?: string;
  requires_owner_approval?: boolean;
  created_at?: string;
  decided_at?: string | null;
  approved_by?: string | null;
  reject_reason?: string | null;
};

export type GovernorProposalsView = {
  proposal_types?: GovernorProposalType[];
  pending: GovernorProposal[];
  pending_count: number;
  pending_by_type?: Record<string, number>;
  history: GovernorProposal[];
  note?: string;
};

export type GovernorTaskPriority = "P0" | "P1" | "P2" | "P3" | "P4";

export type GovernorTaskStatus = "PENDING" | "DONE" | "FAILED";

export type GovernorTaskType =
  | "DATA_QUALITY_REVIEW"
  | "RISK_REVIEW"
  | "MISSED_OPPORTUNITY_REVIEW"
  | "TRADE_REVIEW"
  | "MODE_REVIEW"
  | "SYSTEM_HEALTH_REVIEW";

export type GovernorTask = {
  task_id: string;
  task_type: GovernorTaskType;
  priority: GovernorTaskPriority;
  subject?: string;
  params?: Record<string, unknown>;
  status: GovernorTaskStatus;
  auto_execute?: boolean;
  can_change_policy: boolean;
  source?: string;
  created_at?: string;
  executed_at?: string | null;
  result?: Record<string, unknown> | null;
};

export type GovernorTasksView = {
  task_types?: Record<string, string>;
  queue: GovernorTask[];
  queue_count: number;
  queue_by_priority?: Record<string, number>;
  history: GovernorTask[];
  note?: string;
};

export type GovernorReportSection = {
  available: boolean;
  data?: unknown;
  error?: string;
};

export type GovernorReport = {
  generated_at: string;
  paper_safe: boolean;
  no_execution: boolean;
  learned?: GovernorReportSection;
  found_missed_opportunities?: GovernorReportSection;
  tasks?: GovernorReportSection;
  proposals?: GovernorReportSection;
  other_pending_approvals?: GovernorReportSection;
  data_trust?: GovernorReportSection;
  worker_last_run?: GovernorReportSection;
  note?: string;
};
