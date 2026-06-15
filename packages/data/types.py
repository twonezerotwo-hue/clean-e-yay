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
