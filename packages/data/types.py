"""Veri katmanı için ortak veri tipleri (Pydantic)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


Direction = Literal["bullish", "bearish", "neutral"]
Sentiment = Direction
RegimeLabel = Literal["OFFENSIVE", "NEUTRAL", "DEFENSIVE", "CRISIS"]
AssetStatus = Literal["BLOCKING", "PENDING", "CONFIRMED"]

# T0 — Timeframe = first-class dimension. Sinyal uzayı (symbol, timeframe)
# çiftiyle anahtarlanır; risk/halt portföy seviyesinde global kalır.
Timeframe = Literal["15m", "1h", "4h", "1d", "1w"]
TIMEFRAMES: tuple[Timeframe, ...] = ("15m", "1h", "4h", "1d", "1w")
DEFAULT_TIMEFRAME: Timeframe = "1d"


PriceStatus = Literal["OK", "DATA_UNAVAILABLE", "MOCK"]


class PriceQuote(BaseModel):
    """Tek fiyat noktası.

    `price=None` → veri yok (runtime'da live provider başarısız). Mock
    verisi yalnızca test/dev modunda `status="MOCK"` ile döner;
    runtime'da kullanılmaz.
    """

    symbol: str
    price: float | None = None
    ts: datetime = Field(default_factory=utcnow)
    source: str = "unknown"
    verified: bool = False
    status: PriceStatus = "DATA_UNAVAILABLE"
    error: str | None = None
    fallback: bool = False  # geriye dönük uyumluluk için


class OHLCVBar(BaseModel):
    """Tek mum (T1). `ts` = bar açılış zamanı (UTC).

    `source` resample edilen barlarda `"resampled:<base_tf>"` taşır;
    fixture barları `source="fixture"`, `verified=False` damgalıdır ve
    runtime'da asla üretilmez (DATA_POLICY).
    """

    symbol: str
    timeframe: Timeframe
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str = "unknown"
    verified: bool = False


TechnicalStatus = Literal["OK", "DEGRADED"]


class TechnicalSnapshot(BaseModel):
    symbol: str
    timeframe: Timeframe = "1d"
    rsi: float | None = None
    # T1: macd = MACD(12/26/9) histogramının fiyata normalize edilmiş hali
    # ((macd_line - signal) / close * 100) — semboller arası karşılaştırılabilir.
    macd: float | None = None
    atr: float | None = None
    ema_stack: Literal["bullish", "bearish", "mixed"] | None = None
    score: float = 0.0
    # Top-down GATED direction (0–100, 50 = neutral): momentum trigger gated by
    # location/pattern/volume evidence (build_timeframe_result). None when momentum
    # is insufficient (DATA_POLICY). Consensus `_touche` prefers this over `score`;
    # `score` (legacy RSI+MACD) stays for backward-compat / fallback.
    direction_score: float | None = None
    # Top-down location gate multiplier (1.0 neutral, <1 penalty e.g. shorting into
    # support, >1 confirm) + the compact location evidence behind it (fib zone /
    # confluence / pattern / reversal). Surfaced so the LLM can EXPLAIN the gate in
    # plain language ("bearish momentum but sitting on support — don't short here").
    location_gate: float | None = None
    location_evidence: list[str] = Field(default_factory=list)
    ts: datetime = Field(default_factory=utcnow)
    # T1 additive — bar yetersiz/stale ise DEGRADED; alanlar None kalır.
    status: TechnicalStatus = "OK"
    source: str = "unknown"
    bars_used: int = 0


# ── F1 — Multi-timeframe Fibonacci (technical evidence layer; never decides) ───
# Backend owns Fibonacci meaning: levels are computed from real OHLCV swings here.
# This is additive technical evidence — it does NOT change `technical_score`,
# does NOT open trades, and is NOT consumed by the decision engine / RiskGate.
FibKind = Literal["retracement", "extension"]
FibRole = Literal["support", "resistance", "neutral", "unknown"]
FibTrend = Literal["uptrend", "downtrend", "range", "unknown"]
FibZone = Literal[
    "near_support", "near_resistance", "breakout", "breakdown", "mid_range", "unknown"
]
FibValidity = Literal["sane", "weak", "unavailable"]
FibConfluenceZone = Literal["support", "resistance", "mixed", "none", "unknown"]
FibTF = Literal["1D", "4H"]


class FibonacciLevel(BaseModel):
    ratio: float
    label: str
    price: float
    kind: FibKind
    role: FibRole = "unknown"
    distance_pct: float | None = None


class FibonacciAnalysis(BaseModel):
    timeframe: FibTF
    swing_high: float | None = None
    swing_low: float | None = None
    swing_start: str | None = None
    swing_end: str | None = None
    trend_direction: FibTrend = "unknown"
    levels: list[FibonacciLevel] = Field(default_factory=list)
    nearest_level: FibonacciLevel | None = None
    nearest_distance_pct: float | None = None
    zone: FibZone = "unknown"
    validity: FibValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


class FibonacciConfluence(BaseModel):
    has_confluence: bool = False
    confluence_zone: FibConfluenceZone = "unknown"
    nearest_1d_level: FibonacciLevel | None = None
    nearest_4h_level: FibonacciLevel | None = None
    distance_between_levels_pct: float | None = None
    score: int = 0
    reason: str = ""
    diagnostics: list[str] = Field(default_factory=list)


class TechnicalInsight(BaseModel):
    """Per-symbol technical evidence aggregate carrying the Fibonacci layer.

    Additive: it does not alter the per-TF `TechnicalSnapshot.score`
    (`technical_score`). `fibonacci_score` (0–25) is a separate evidence signal.
    """
    symbol: str
    fib_1d: FibonacciAnalysis | None = None
    fib_4h: FibonacciAnalysis | None = None
    fib_confluence: FibonacciConfluence | None = None
    fibonacci_score: int = 0


# ── T-MTF — Per-timeframe technical result (multi-TF feature; never decides) ───
# One structured technical opinion per (symbol, closed-candle timeframe). EVIDENCE
# only: indicators are computed from real closed OHLCV here. It does NOT open
# trades, is NOT consumed as a single aggregated score, and is NOT the RiskGate.
# CORE RULE: direction and strength are SEPARATE axes — there is no one
# "aggregated_technical_score" that represents every strategy. Missing/insufficient
# data becomes diagnostics (indicator_quality / warnings), NEVER a fake neutral
# confidence (DATA_POLICY).
IndicatorQuality = Literal["OK", "INSUFFICIENT_HISTORY"]
TechnicalBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]
# Per-TF (price-derived) volatility regime — distinct from the macro regime
# (packages/regime, price-OFF). UNKNOWN = could not be computed (no fake value).
TfVolatilityRegime = Literal["TRENDING", "RANGING", "SQUEEZE", "EXPANSION", "UNKNOWN"]
TrendStrengthLabel = Literal["TRENDING", "WEAK", "UNKNOWN"]


class IndicatorQualityReport(BaseModel):
    """Per-indicator warm-up status — INSUFFICIENT_HISTORY is a diagnostic, not a
    fake value. Missing M15 must not collapse D1/H4/H1 (graceful degradation)."""

    rsi: IndicatorQuality = "INSUFFICIENT_HISTORY"
    macd: IndicatorQuality = "INSUFFICIENT_HISTORY"
    ema200: IndicatorQuality = "INSUFFICIENT_HISTORY"
    atr: IndicatorQuality = "INSUFFICIENT_HISTORY"
    adx: IndicatorQuality = "INSUFFICIENT_HISTORY"


class TechnicalDataQuality(BaseModel):
    status: TechnicalStatus = "DEGRADED"
    bars_used: int = 0
    stale: bool = False
    indicator_quality: IndicatorQualityReport = Field(default_factory=IndicatorQualityReport)
    warnings: list[str] = Field(default_factory=list)


class TechnicalScoreOverview(BaseModel):
    """Two SEPARATE axes — never collapsed into one aggregate (architecture rule).

    `direction_score` 0–100 (50 = neutral); `strength_score` 0–100 (conviction).
    `None` means insufficient data — NOT a neutral 50 (DATA_POLICY)."""

    direction_score: float | None = None
    strength_score: float | None = None
    # Diagnostic (NOT a collapsed score): how much the top-down location/pattern/
    # volume gate scaled momentum conviction. 1.0 = neutral, <1 penalty (e.g. longing
    # into resistance), >1 mild confirm. None when momentum/evidence insufficient.
    location_gate_multiplier: float | None = None
    # Faz 2 chop guard — momentum yönü gerçek trend yokken (ADX düşük) ne kadar
    # söndü/sönerdi (gözlem; <1.0 = chop sönümü). enabled OFF iken de dolu (shadow);
    # None = chop değil / adx yok. Öğrenme katmanı bunu İZLEMEZ — manuel tespit alanı.
    chop_guard_multiplier: float | None = None
    # Faz 3a exhaustion guard — momentum climax'ı (aynı yönde tükenme) kovalarken ne
    # kadar söndü/sönerdi (gözlem; <1.0). enabled OFF iken de dolu (shadow); None =
    # kovalama yok / veri yok. Manuel tespit alanı (öğrenme katmanı izlemez).
    exhaustion_guard_multiplier: float | None = None
    # Faz 3b reversion — uç tükenme + reversal teyidi varsa yönün ÇEVRİLECEĞİ skor
    # (gözlem; >50 long-reversion, <50 short-reversion). enabled OFF iken de dolu
    # (shadow); None = reversion setup'ı yok. Risk-yaratır → owner enable kararı.
    reversion_score: float | None = None


class TechnicalKeyLevels(BaseModel):
    support: float | None = None
    resistance: float | None = None
    atr: float | None = None
    atr_percent: float | None = None
    stop_reference: float | None = None
    target_reference: float | None = None


class TechnicalTrendStrength(BaseModel):
    """ADX-band trend reality (NOT direction). adx < adx_trend_min → trend-follow
    signals are weakened; levels/reversals gain weight (architecture gate)."""

    adx: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    is_trending: bool = False
    label: TrendStrengthLabel = "UNKNOWN"


class TechnicalConfluenceZone(BaseModel):
    """Per-TF confluence: fib + S/R + VWAP clustering in the same price band."""

    price: float
    kind: Literal["support", "resistance"]
    components: list[str] = Field(default_factory=list)


class ConfirmationSignal(BaseModel):
    """A TIMING gate ('triggered or not') — separate from scoring (no double count).
    The same EMA/volume magnitude is scored once in score_overview; here we only
    say whether a trigger fired (section 4.4)."""

    name: str
    fired: bool = False
    detail: str = ""


class TechnicalTimeframeSummary(BaseModel):
    bias: TechnicalBias = "NEUTRAL"
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Reversal + chart-pattern layers (section 4.5) — EVIDENCE only, never trades ──
# Computed from real closed bars (momentum divergence / swing structure). Like the
# fibonacci layer, they enrich the per-TF result but never open a trade, never feed a
# single aggregate score, and are not the RiskGate. Insufficient bars → None (the
# field is absent, never a fabricated NEUTRAL).
ReversalType = Literal[
    "rsi_bullish_divergence",
    "rsi_bearish_divergence",
    "macd_bullish_divergence",
    "macd_bearish_divergence",
    "double_bottom",
    "double_top",
]
ChartPatternName = Literal["uptrend_structure", "downtrend_structure", "ranging"]


class ReversalSignal(BaseModel):
    """One detected reversal cue (momentum divergence or double formation)."""

    type: ReversalType
    detected: bool = True
    detail: str = ""


class TechnicalReversalSignals(BaseModel):
    """Reversal cues from real closed bars; `bias` is the net direction (NEUTRAL when
    none or conflicting). EVIDENCE only — never opens or sizes a trade."""

    signals: list[ReversalSignal] = Field(default_factory=list)
    bias: TechnicalBias = "NEUTRAL"


class ChartPattern(BaseModel):
    name: ChartPatternName
    detail: str = ""


class TechnicalChartPatterns(BaseModel):
    """Price-structure read from swing pivots (HH/HL vs LH/LL). EVIDENCE only."""

    active_patterns: list[ChartPattern] = Field(default_factory=list)
    bias: TechnicalBias = "NEUTRAL"


class TechnicalTimeframeResult(BaseModel):
    """Canonical per-(symbol, timeframe) technical result (contract section 5).

    Reversal (momentum divergence + double formations) and chart-pattern (swing
    structure) layers (section 4.5) are computed from real closed bars; insufficient
    history → the field is None (absent), never a fabricated value. `fibonacci_analysis`
    is only attached for 4H/1D (its per-TF semantics). EVIDENCE only — never trades."""

    symbol: str
    timeframe: Timeframe
    data_quality: TechnicalDataQuality = Field(default_factory=TechnicalDataQuality)
    score_overview: TechnicalScoreOverview = Field(default_factory=TechnicalScoreOverview)
    key_levels: TechnicalKeyLevels = Field(default_factory=TechnicalKeyLevels)
    confirmation_signals: list[ConfirmationSignal] = Field(default_factory=list)
    trend_strength: TechnicalTrendStrength = Field(default_factory=TechnicalTrendStrength)
    volatility_regime: TfVolatilityRegime = "UNKNOWN"
    confluence_zones: list[TechnicalConfluenceZone] = Field(default_factory=list)
    timeframe_summary: TechnicalTimeframeSummary = Field(default_factory=TechnicalTimeframeSummary)
    fibonacci_analysis: FibonacciAnalysis | None = None
    reversal_signals: TechnicalReversalSignals | None = None
    chart_pattern_analysis: TechnicalChartPatterns | None = None
    status: TechnicalStatus = "OK"
    source: str = "unknown"
    ts: datetime = Field(default_factory=utcnow)


# ── T2 — TechnicalAgent output (one structured opinion per symbol) ─────────────
# Consumes per-TF TechnicalTimeframeResult and emits a single agent view. It does
# NOT open trades, NOT size positions, and is NOT the RiskGate. Missing/degraded
# inputs → ABSTAIN/DEGRADED + missing_data (never a fabricated confident opinion).
# `direction_score`/`strength_score` are COARSE summaries; `per_timeframe` detail
# stays authoritative and consensus does the strategy-specific combination.
TechnicalStance = Literal["ALLOW", "CAUTION", "ABSTAIN", "DEGRADED"]


class TechnicalInvalidation(BaseModel):
    timeframe: Timeframe | None = None
    price: float | None = None
    reason: str = ""


class TechnicalAgentOutput(BaseModel):
    agent: Literal["technical"] = "technical"
    symbol: str
    # keys: m15 / h1 / h4 / d1 / w1 (contract naming)
    per_timeframe: dict[str, TechnicalTimeframeResult] = Field(default_factory=dict)
    stance: TechnicalStance = "ABSTAIN"
    direction_score: float | None = None
    strength_score: float | None = None
    used_observations: list[str] = Field(default_factory=list)
    invalidation: TechnicalInvalidation | None = None
    missing_data: list[str] = Field(default_factory=list)
    ts: datetime = Field(default_factory=utcnow)


# ── T2 — Cross-timeframe consensus snapshot (TF + agent aggregation) ───────────
# Aggregates per-TF technical results into one asset view. SEPARATE axes
# (direction / strength / agreement / alignment) — never one collapsed score for
# all strategies. NEUTRAL biases DILUTE alignment; countertrend is CONDITIONAL
# (only when higher-TF bias and lower-TF signal disagree in sign). EVIDENCE only:
# never opens trades, never sizes, not the RiskGate.
AlignmentStatus = Literal["ALIGNED", "PARTIAL", "COUNTERTREND", "CONFLICTED"]


class CrossTimeframeConfluenceZone(BaseModel):
    """A price band where ≥2 timeframes' levels cluster (e.g. 4H support + 1D fib)."""

    price: float
    kind: Literal["support", "resistance"]
    timeframes: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)


class ConsensusSnapshot(BaseModel):
    asset: str
    # per-TF bias keyed m15/h1/h4/d1/w1 (NEUTRAL included)
    per_timeframe_bias: dict[str, TechnicalBias] = Field(default_factory=dict)
    alignment_status: AlignmentStatus = "CONFLICTED"
    alignment_score: float = 0.0          # 0..100 weighted directional consensus (NEUTRAL dilutes)
    cross_timeframe_confluence: list[CrossTimeframeConfluenceZone] = Field(default_factory=list)
    direction_score: float | None = None  # weighted across TFs (50=neutral); None=insufficient
    strength_score: float | None = None
    agreement_score: float = 0.0          # unanimity among directional TFs (0..100)
    is_countertrend: bool = False
    confirmed_count: int = 0
    pending_count: int = 0
    blocking_count: int = 0
    evidence: list[str] = Field(default_factory=list)
    ts: datetime = Field(default_factory=utcnow)


# ── T2 — AgentDecision (deterministic action; RiskGate stays final) ────────────
# Bridges consensus EVIDENCE → one high-level action + entry_timeframe. It does
# NOT open trades (paper open is the matrix/RiskGate's job) and `risk_gate_required`
# is always true. Upper TF only SCALES DOWN (size_multiplier ≤ 1.0, never boosts);
# 1w yields bias only (no entry); countertrend is never an automatic full entry.
DecisionAction = Literal[
    "NO_TRADE", "WATCH", "SCOUT_ALLOWED", "CONFIRMATION_REQUIRED", "RISK_REDUCE", "KILL_SWITCH"
]


class AgentDecision(BaseModel):
    asset: str
    action: DecisionAction = "NO_TRADE"
    entry_timeframe: Timeframe | None = None
    size_multiplier: float = 0.0          # ≤1.0 — upper TF only scales DOWN
    confidence: float = 0.0               # 0..1
    reason: str = ""
    supporting_agents: list[str] = Field(default_factory=list)
    blocking_agents: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(default_factory=list)
    manual_ready_required: bool = False
    risk_gate_required: bool = True
    ts: datetime = Field(default_factory=utcnow)


# P0 parity — başlık tazeliği yayın yaşına göre damgalanır (UI hesap yapmaz).
NewsFreshness = Literal["FRESH", "RECENT", "STALE"]


class NewsHeadline(BaseModel):
    """Tek haber başlığı.

    P0 parity: runtime'da yalnızca gerçek RSS'ten gelen başlıklar
    `verified=True` taşır. `verified=False` başlıklar (fixture/test)
    consensus news skoruna GİRMEZ (DATA_POLICY).
    `asset_impact`: sembol → yön (-1.0 bearish / 0.0 nötr / +1.0 bullish).
    """

    id: str
    source: str
    region: str | None = None
    ts: datetime
    title: str
    title_tr: str | None = None
    sentiment: Sentiment | None = None
    asset_impact: dict[str, float] = Field(default_factory=dict)
    url: str | None = None
    verified: bool = False
    freshness: NewsFreshness | None = None
    error: str | None = None


class Catalyst(BaseModel):
    """Takvim olayı (event calendar).

    P0 parity: runtime'da yalnızca `config/event_calendar.yaml`'dan okunan
    olaylar `verified=True` taşır. Event risk gate'i sadece verified +
    high/critical olayları sayar ve yalnızca kısıtlayıcıdır.
    """

    id: str
    ts: datetime
    title: str
    importance: Literal["low", "medium", "high", "critical"] = "low"
    region: str | None = None
    category: str | None = None
    market_impact: str | None = None
    days_until: int | None = None
    hours_until: float | None = None
    source: str = "unknown"
    verified: bool = False


# v2.7 D5 — Catalyst half-life intelligence. Haber → catalyst sınıflandırması.
# Kural tabanlı/deterministik (LLM YOK). Yalnızca kısıtlayıcı taksonomi:
#   CONTEXT_ONLY         → yalnızca bağlam (karar zincirine girmez)
#   WATCH                → uyarı (size değişmez)
#   CAUTION              → size ×0.5
#   NO_POSITION_INCREASE → yeni pozisyon açılışı durur (block)
CatalystActionability = Literal[
    "CONTEXT_ONLY", "WATCH", "CAUTION", "NO_POSITION_INCREASE"
]

# Kural tabanlı event_type taksonomisi (deterministik; rumor/unknown dâhil).
CatalystEventType = Literal[
    "geopolitical_deescalation",
    "geopolitical_escalation",
    "inflation_data",
    "jobs_data",
    "central_bank",
    "oil_supply",
    "oil_inventory",
    "crypto_etf_flow",
    "funding_oi_squeeze",
    "earnings",
    "exchange_outage",
    "rumor_unverified",
    "unknown",
]


class CatalystImpact(BaseModel):
    """v2.7 D5 — Catalyst half-life intelligence (haber → etki modeli).

    Haber başlığı kural tabanlı (deterministik, LLM YOK) bir `event_type`'a
    sınıflandırılır ve event_type'a göre asset × timeframe etki haritası +
    yarı-ömür (half-life) + geçerlilik (valid_until) üretilir.

    Karar zincirinde **yalnızca kısıtlayıcı** (WATCH / CAUTION /
    NO_POSITION_INCREASE) veya yalnızca bağlam (CONTEXT_ONLY) etkisi yapar —
    ASLA size artırmaz, ASLA RiskGate/DQS/KillSwitch/halt'ı bypass etmez.

    DATA_POLICY: yalnızca `verified=True` impact karar zincirine girer. Doğrulanmamış
    haber (fixture) ve **rumor** (`rumor_unverified`) `verified=False` damgalıdır ve
    yalnızca dashboard bağlamı sağlar — trade'e dönüşmez. Yarı-ömrü dolan
    (`now > valid_until`) catalyst de karar zincirine girmez (yalnızca bağlam).
    """

    catalyst_id: str
    headline_id: str = ""
    event_type: CatalystEventType = "unknown"
    surprise_level: float = 0.0     # -1..+1 (piyasa yönü işaretli; |.| = şiddet)
    affected_assets: list[str] = Field(default_factory=list)
    expected_half_life_minutes: int = 60
    affected_timeframes: list[Timeframe] = Field(default_factory=list)
    timeframe_bias: dict[Timeframe, Direction] = Field(default_factory=dict)
    valid_until: datetime | None = None
    decay_curve: Literal["exponential", "linear", "step"] = "exponential"
    confidence: float = 0.0         # 0..1 (kaynak doğrulaması + tazelik)
    actionability: CatalystActionability = "CONTEXT_ONLY"
    verified: bool = False
    source: str = "unknown"
    region: str | None = None
    freshness: NewsFreshness | None = None
    ts: datetime = Field(default_factory=utcnow)
    evidence: list[str] = Field(default_factory=list)


# v2.7 D2 — Crypto Derivatives Intelligence (funding / OI / squeeze proxy).
DerivativesStatus = Literal["OK", "DEGRADED"]
SqueezeLevel = Literal["NONE", "LOW", "ELEVATED", "HIGH"]
FundingBias = Literal["crowded_long", "crowded_short", "neutral"]


class DerivativesSnapshot(BaseModel):
    """Tek kripto sembol için türev (derivatives) zekâsı.

    v2.7 D2: funding rate + open interest + squeeze proxy. **Yalnızca kripto
    sembolleri** için üretilir ve karar zincirinde **yalnızca kısıtlayıcı**
    (CAUTION / size-reduce) veya bağlam etkisi yapar — asla size artırmaz,
    asla RiskGate/DQS/halt'ı bypass etmez.

    `squeeze_proxy` GERÇEK liquidation API'si DEĞİLDİR — funding + OI değişimi +
    fiyat momentumu + volatiliteden türetilen bir vekildir (`is_proxy=True`,
    açıkça "proxy" etiketli; gerçek liquidation diye sunulmaz).

    DATA_POLICY: runtime'da yalnızca gerçek (live) veri `verified=True` taşır.
    Live provider başarısız olursa `status="DEGRADED"`, alanlar None — mock
    üretilmez, crash olmaz. Fixture verisi `verified=False` damgalıdır ve
    karar zincirine GİRMEZ (yalnızca dashboard bağlamı).
    """

    symbol: str
    funding_rate: float | None = None          # 8s interval, ondalık (0.0001 = %0.01)
    funding_annualized: float | None = None     # bağlam (≈ funding_rate × 3 × 365)
    open_interest_usd: float | None = None
    oi_change_pct: float | None = None          # önceki gözleme göre OI değişimi
    price_momentum_pct: float | None = None     # kısa vadeli (1h) fiyat momentumu
    volatility_pct: float | None = None         # ATR/fiyat (normalize)
    squeeze_proxy: float = 0.0                   # 0..100 (PROXY — gerçek liq değil)
    squeeze_level: SqueezeLevel = "NONE"
    funding_bias: FundingBias = "neutral"
    is_proxy: bool = True                        # squeeze her zaman proxy
    status: DerivativesStatus = "DEGRADED"
    source: str = "unknown"
    verified: bool = False
    freshness: NewsFreshness | None = None       # FRESH / RECENT / STALE
    dqs: float = 0.0                             # bu sembolün türev veri kalitesi (0..100)
    ts: datetime = Field(default_factory=utcnow)
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


# v2.7 D4 — Realized Volatility / Volatility Regime Intelligence.
VolatilityStatus = Literal["OK", "DEGRADED"]
VolatilityRegime = Literal["LOW", "NORMAL", "ELEVATED", "EXTREME"]
# Vol squeeze / expansion / shock bağlam bayrağı (normal = sıradan rejim).
VolState = Literal["normal", "squeeze", "expansion", "shock"]


class VolatilitySnapshot(BaseModel):
    """Tek (symbol, timeframe) için realized volatility + rejim zekâsı.

    v2.7 D4: mevcut OHLCV cache'inden (ekstra ağ yok) log-getiri tabanlı
    annualize realized volatility, rolling pencereler (short/medium/long),
    volatilite z-score'u, rejim (LOW/NORMAL/ELEVATED/EXTREME) ve
    squeeze/expansion/shock bağlam bayrağı hesaplanır.

    Karar zincirinde **yalnızca kısıtlayıcı** (CAUTION / size-reduce /
    NO_POSITION_INCREASE) veya bağlam etkisi yapar — asla size artırmaz,
    asla RiskGate/DQS/halt'ı bypass etmez. 15m/1h için vol shock daha etkili;
    1d/1w için rejim bağlamı.

    DATA_POLICY: runtime'da yalnızca gerçek (live) OHLCV `verified=True` taşır.
    Bar yetersiz → `status="DEGRADED"`, alanlar None (mock yok, crash yok).
    Fixture barlar `verified=False` damgalıdır ve karar zincirine GİRMEZ
    (yalnızca dashboard bağlamı).
    """

    symbol: str
    timeframe: Timeframe = "1d"
    realized_vol: float | None = None        # annualize medium-pencere realized vol (0.65 = %65)
    rv_short: float | None = None            # kısa pencere annualize realized vol
    rv_medium: float | None = None
    rv_long: float | None = None             # uzun pencere (baseline) annualize realized vol
    vol_zscore: float | None = None          # rv_short'un kendi geçmişine göre z-skoru
    regime: VolatilityRegime = "NORMAL"
    vol_state: VolState = "normal"
    status: VolatilityStatus = "DEGRADED"
    source: str = "unknown"
    verified: bool = False
    freshness: NewsFreshness | None = None   # FRESH / RECENT / STALE
    dqs: float = 0.0                         # bu hücrenin vol veri kalitesi (0..100)
    bars_used: int = 0
    ts: datetime = Field(default_factory=utcnow)
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


# v2.7 D3 — Options IV / Skew / Implied Volatility Intelligence (BTC/ETH).
OptionsStatus = Literal["OK", "DEGRADED", "UNAVAILABLE"]
# Options stress rejimi (yalnızca kısıtlayıcı / bağlam sınıfı):
#   NORMAL              → sıradan; etki yok
#   RICH_VOL            → IV >> realized (pahalı vol; risk primi yüksek → size kısıtı)
#   CHEAP_VOL           → IV < realized (ucuz vol; yalnızca bağlam, boost YOK)
#   PUT_SKEW_STRESS     → put'lar call'lardan pahalı (downside korku → long CAUTION)
#   CALL_SKEW_EUPHORIA  → call'lar put'lardan pahalı (öfori → long chase CAUTION)
#   TERM_STRESS         → ön vade IV > uzun vade (backwardation; yakın stres → WATCH/block)
OptionsRegime = Literal[
    "NORMAL", "RICH_VOL", "CHEAP_VOL",
    "PUT_SKEW_STRESS", "CALL_SKEW_EUPHORIA", "TERM_STRESS",
]


class OptionsSnapshot(BaseModel):
    """Tek kripto sembol için options (IV / skew / term structure) zekâsı.

    v2.7 D3: Deribit (veya fixture) options chain'inden ATM implied volatility,
    25Δ skew / risk-reversal proxy, put/call open-interest oranı, term structure
    (front/next/long vade IV) ve realized-vs-implied spread (D4 realized vol ile)
    hesaplanır; bir options stress rejimine sınıflandırılır.

    Karar zincirinde **yalnızca kripto sembolleri** (BTCUSD/ETHUSD) için ve
    **yalnızca kısıtlayıcı** (CAUTION / size-reduce / NO_POSITION_INCREASE) veya
    bağlam etkisi yapar — ASLA size artırmaz, ASLA RiskGate/DQS/halt'ı bypass
    etmez. Options daha çok 4h/1d/1w bağlamıdır (15m/1h düşük ağırlık).

    `skew_25d` GERÇEK delta-greeks DEĞİLDİR — moneyness tabanlı bir **proxy**'dir
    (`is_proxy=True`): ön vadede OTM call IV − OTM put IV (risk reversal; negatif =
    put skew / korku).

    DATA_POLICY: runtime'da yalnızca gerçek (live) veri `verified=True` taşır.
    Live provider başarısız → `status="DEGRADED"`/`"UNAVAILABLE"`, alanlar None
    (mock yok, crash yok). Fixture verisi `verified=False` (yalnızca dashboard
    bağlamı; karar zincirine GİRMEZ).
    """

    symbol: str
    underlying_price: float | None = None
    atm_iv: float | None = None              # ön vade ATM implied vol (annualize ondalık; 0.55 = %55)
    realized_vol: float | None = None        # karşılaştırma için (D4 realized vol, annualize ondalık)
    iv_rv_spread: float | None = None        # atm_iv − realized_vol (pozitif = IV pahalı)
    skew_25d: float | None = None            # risk reversal proxy = call_iv − put_iv (negatif = put skew)
    put_call_oi_ratio: float | None = None   # toplam put OI / toplam call OI
    term_front_iv: float | None = None       # en yakın vade ATM IV
    term_next_iv: float | None = None        # bir sonraki vade ATM IV
    term_long_iv: float | None = None        # uzun vade ATM IV
    term_slope: float | None = None          # term_long_iv − term_front_iv (negatif = backwardation)
    front_expiry: str | None = None
    next_expiry: str | None = None
    long_expiry: str | None = None
    contracts_used: int = 0
    regime: OptionsRegime = "NORMAL"
    is_proxy: bool = True                    # skew her zaman moneyness proxy (gerçek 25Δ greeks değil)
    status: OptionsStatus = "DEGRADED"
    source: str = "unknown"
    verified: bool = False
    freshness: NewsFreshness | None = None   # FRESH / RECENT / STALE
    dqs: float = 0.0                         # bu sembolün options veri kalitesi (0..100)
    ts: datetime = Field(default_factory=utcnow)
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


RotationStatus = Literal["OK", "UNAVAILABLE"]


class RotationView(BaseModel):
    """Sermaye rotasyonu görünümü.

    P0 parity: skor gerçek OHLCV (1d) momentum + çapraz oran analizinden
    gelir. Veri yetersizse `status="UNAVAILABLE"` — consensus quantum
    modülü düşer ve ağırlık redistribute edilir; mock skor üretilmez.
    """

    name: str = "Sermaye Rotasyonu"
    score: float = 50.0
    direction: Direction = "neutral"
    evidence: list[str] = Field(default_factory=list)
    status: RotationStatus = "OK"
    source: str = "unknown"
    verified: bool = False
    error: str | None = None


# --------------------------------------------------------------------------
# Elliott Wave Scenario Engine — EVIDENCE only (packages/elliott).
#
# Gerçek OHLCV barlarından fraktal pivot dizisi + Elliott impulse/correction
# kural kontrolü ile bir senaryo üretir. NEVER opens a trade, NEVER bypasses
# RiskGate, NEVER feeds a single aggregate score — Fibonacci provider'ın
# (packages/data/providers/technical/fibonacci.py) izlediği "evidence only,
# validity/diagnostics, uydurma seviye yok" desenini birebir takip eder.
# Hiçbir setup'ın ön koşulu DEĞİLDİR: NO_VALID_COUNT dönerse çağıran taraf
# (decision/agent_pipeline) diğer kanıtlarla devam edebilir — bu modül bunu
# zorlamaz, sadece kendi kanıtını üretir.
# --------------------------------------------------------------------------

ElliottScenarioType = Literal[
    "IMPULSE_1_2_3_4_5",
    "IMPULSE_5_ENDING",
    "ABC_CORRECTION",
    "NO_VALID_COUNT",
]
ElliottBias = Literal["REVERSAL_LONG", "REVERSAL_SHORT", "CONTINUATION", "unknown"]
ElliottDegree = Literal["minor", "intermediate", "unknown"]


class ElliottWavePoint(BaseModel):
    """Senaryoyu oluşturan tek pivot — dizideki sırasıyla (P0..P5 veya A/B/C)."""

    label: str
    bar_index: int
    price: float
    ts: str | None = None


class ElliottAnalysis(BaseModel):
    timeframe: str
    primary_scenario: ElliottScenarioType = "NO_VALID_COUNT"
    confidence: float = 0.0  # 0-100; rule-pass oranından türetilir
    wave_points: list[ElliottWavePoint] = Field(default_factory=list)
    invalidation_price: float | None = None
    target_zone: tuple[float, float] | None = None
    bias: ElliottBias = "unknown"
    degree: ElliottDegree = "unknown"
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Zone Engine — EVIDENCE only (packages/zones).
#
# Genel support/resistance zone tespiti: yakın fraktal swing pivotları
# kümeleyerek bölge (tek seviye değil, fiyat aralığı) üretir. Spec §12'deki
# "tek fiyat seviyesi yerine bölge mantığı" prensibini, mevcut Fibonacci
# provider'ın (fib_cluster_zone hariç — o zaten fibonacci.py'de var) izlediği
# "evidence only, validity/diagnostics, uydurma seviye yok" deseniyle
# tamamlar. Supply/demand zone tespiti bu MVP'nin kapsamı DIŞINDADIR (ayrı,
# daha büyük bir iş — bilinçli olarak eklenmedi, "weak"/"unavailable" ile
# karıştırılmasın diye burada açıkça not edilir).
# --------------------------------------------------------------------------

ZoneKind = Literal["support", "resistance"]
ZoneLocation = Literal[
    "near_support", "near_resistance", "mid_range", "breakout", "breakdown", "unknown"
]
ZoneValidity = Literal["sane", "weak", "unavailable"]


class PriceZone(BaseModel):
    kind: ZoneKind
    price_low: float
    price_high: float
    touches: int = 1
    distance_pct: float | None = None


class ZoneAnalysis(BaseModel):
    timeframe: str
    zones: list[PriceZone] = Field(default_factory=list)
    nearest_zone: PriceZone | None = None
    location: ZoneLocation = "unknown"
    range_high: float | None = None
    range_low: float | None = None
    validity: ZoneValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Volume Validation Engine — EVIDENCE only (packages/volume). Spec §15.
# --------------------------------------------------------------------------

VolumeState = Literal[
    "VOLUME_CLIMAX", "VOLUME_CONFIRMATION", "VOLUME_WEAKENING", "VOLUME_CONFLICT", "VOLUME_NEUTRAL"
]
VolumeValidity = Literal["sane", "weak", "unavailable"]


class VolumeAnalysis(BaseModel):
    timeframe: str
    state: VolumeState = "VOLUME_NEUTRAL"
    volume_ratio: float | None = None  # son bar hacmi / önceki ortalama
    price_direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    trend_direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    validity: VolumeValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# VWAP / Anchored VWAP Engine — EVIDENCE only (packages/vwap). Spec §16.
# --------------------------------------------------------------------------

VWAPLocation = Literal["above", "below", "at", "unknown"]
VWAPValidity = Literal["sane", "weak", "unavailable"]


class AnchoredVWAPLevel(BaseModel):
    anchor: Literal["major_high", "major_low", "volume_climax"]
    anchor_bar_index: int
    vwap_price: float
    location: VWAPLocation = "unknown"
    distance_pct: float | None = None


class VWAPAnalysis(BaseModel):
    timeframe: str
    session_vwap: float | None = None
    location: VWAPLocation = "unknown"
    deviation_pct: float | None = None
    deviation_extreme: bool = False
    reclaim: bool = False  # son N barda alttan üste geçiş
    rejection: bool = False  # son N barda üstten dokunup geri altına dönüş
    anchored: list[AnchoredVWAPLevel] = Field(default_factory=list)
    validity: VWAPValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Liquidity Sweep Engine — EVIDENCE only (packages/liquidity/sweep.py). Spec §13.
# --------------------------------------------------------------------------

LiquiditySweepState = Literal[
    "NO_SWEEP", "LOW_SWEEP_RECLAIMED", "HIGH_SWEEP_RECLAIMED", "LOW_SWEEP_PENDING", "HIGH_SWEEP_PENDING"
]
LiquiditySweepValidity = Literal["sane", "weak", "unavailable"]


class LiquiditySweepAnalysis(BaseModel):
    timeframe: str
    state: LiquiditySweepState = "NO_SWEEP"
    swing_high: float | None = None
    swing_low: float | None = None
    sweep_price: float | None = None
    reclaim_price: float | None = None
    bias: Literal["REVERSAL_LONG", "REVERSAL_SHORT", "unknown"] = "unknown"
    validity: LiquiditySweepValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Exhaustion Score — EVIDENCE only (packages/scoring/exhaustion.py). Spec §17.
#
# Yön skoru DEĞİLDİR: 0 downside exhaustion (long reversal bölgesi), 50 nötr,
# 100 upside exhaustion (short reversal bölgesi). RSI extreme + son-N-bar
# getirisi + volume climax + liquidity sweep kanıtlarını birleştirir.
# --------------------------------------------------------------------------

ExhaustionValidity = Literal["sane", "weak", "unavailable"]


class ExhaustionAnalysis(BaseModel):
    timeframe: str
    score: float = 50.0  # 0..100
    rsi: float | None = None
    recent_return_pct: float | None = None
    contributions: list[str] = Field(default_factory=list)
    validity: ExhaustionValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Location Score — EVIDENCE only (packages/scoring/location.py). Spec §18.
#
# Zone Engine + Fibonacci + VWAP + Liquidity Sweep kanıtlarını birleştirip
# 0-100 tek bir "giriş kalitesi" skoruna indirger. Supply/demand zone bu
# sürümün kapsamı dışında (Zone Engine'le aynı bilinçli sınırlama).
# --------------------------------------------------------------------------

LocationClass = Literal["GOOD_LOCATION", "MID_RANGE", "BAD_LOCATION", "unknown"]
LocationScoreValidity = Literal["sane", "weak", "unavailable"]


class LocationScoreAnalysis(BaseModel):
    score: float = 50.0  # 0..100
    location_class: LocationClass = "unknown"
    contributions: list[str] = Field(default_factory=list)
    validity: LocationScoreValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Trigger Engine — EVIDENCE only (packages/scoring/trigger.py). Spec §22.
#
# Mum formasyonu (engulfing/pin bar) + hacim teyidi + VWAP reclaim/rejection +
# liquidity sweep reclaim kanıtlarını birleştirip tek bir trigger_score (0-100)
# ve TRIGGER_CONFIRMED/MISSING/FAILED durumuna indirger.
# --------------------------------------------------------------------------

TriggerState = Literal["TRIGGER_CONFIRMED", "TRIGGER_MISSING", "TRIGGER_FAILED"]
TriggerValidity = Literal["sane", "weak", "unavailable"]


class TriggerAnalysis(BaseModel):
    timeframe: str
    state: TriggerState = "TRIGGER_MISSING"
    trigger_score: float = 0.0  # 0..100
    matched_triggers: list[str] = Field(default_factory=list)
    validity: TriggerValidity = "unavailable"
    diagnostics: list[str] = Field(default_factory=list)
