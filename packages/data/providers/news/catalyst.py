"""v2.7 D5 — Catalyst half-life intelligence (haber → etki modeli).

Bir `NewsHeadline`'ı kural tabanlı (deterministik, LLM YOK, network YOK) bir
`event_type`'a sınıflandırır ve event_type'a göre asset × timeframe etki haritası
+ yarı-ömür (half-life) + geçerlilik (`valid_until`) + actionability üretir.

Politika ([docs/DATA_POLICY.md], [docs/SAFETY_RULES.md]):
- Catalyst impact karar zincirine **yalnızca kısıtlayıcı** girer (WATCH / CAUTION
  / NO_POSITION_INCREASE) veya yalnızca bağlam (CONTEXT_ONLY). ASLA size artırmaz.
- Yalnızca `verified=True` impact karar zincirine girer. **Rumor** (doğrulanmamış
  söylenti) `verified=False` → CONTEXT_ONLY → trade'e dönüşmez.
- `timeframe_bias` yalnızca bağlamdır (sunum/analytics); gate yön bağımsız
  kısıtlayıcıdır — bias asla size artırmaya kullanılmaz.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from packages.data.providers.news import classify
from packages.data.types import (
    CatalystActionability,
    CatalystEventType,
    CatalystImpact,
    Direction,
    NewsHeadline,
    Timeframe,
    utcnow,
)

# ---------------------------------------------------------------------------
# event_type sınıflandırma — sıralı kural seti (ilk eşleşen kazanır).
# Deterministik: aynı başlık her zaman aynı event_type'ı verir.
# ---------------------------------------------------------------------------

_RUMOR_WORDS: Final[tuple[str, ...]] = (
    "rumor", "rumour", "unconfirmed", "unverified", "speculation", "speculat",
    "alleged", "reportedly", "sources say", "could", "may ", "might ",
    "söylenti", "iddia", "doğrulanmamış", "spekülasyon",
)
_DEESCALATION_WORDS: Final[tuple[str, ...]] = (
    "ceasefire", "truce", "peace deal", "peace talks", "de-escalat",
    "deescalat", "hostage release", "agreement reached", "diplomatic",
    "ateşkes", "barış", "müzakere",
)
_ESCALATION_WORDS: Final[tuple[str, ...]] = (
    "airstrike", "missile", "invasion", "offensive", "attack", "strike on",
    "drone strike", "blockade", "retaliat", "escalat", "war", "military operation",
    "saldırı", "füze", "işgal", "savaş", "askeri operasyon",
)
_INFLATION_WORDS: Final[tuple[str, ...]] = (
    "cpi", "pce", "inflation", "consumer price", "ppi", "producer price",
    "enflasyon", "tüfe", "üfe",
)
_JOBS_WORDS: Final[tuple[str, ...]] = (
    "nonfarm", "non-farm", "payroll", "jobs report", "unemployment rate",
    "jobless claims", "labor market", "istihdam", "işsizlik",
)
_CENTRAL_BANK_WORDS: Final[tuple[str, ...]] = (
    "fomc", "federal reserve", "fed ", "powell", "rate decision", "rate hike",
    "rate cut", "ecb", "central bank", "lagarde", "boj", "bank of england",
    "monetary policy", "faiz kararı", "merkez bankası",
)
_OIL_SUPPLY_WORDS: Final[tuple[str, ...]] = (
    "opec", "opec+", "production cut", "output cut", "supply cut", "oil supply",
    "üretim kısıntısı", "arz",
)
_OIL_INVENTORY_WORDS: Final[tuple[str, ...]] = (
    "eia", "crude inventory", "inventories", "stockpile", "api crude",
    "stok", "envanter",
)
_ETF_FLOW_WORDS: Final[tuple[str, ...]] = (
    "etf flow", "etf inflow", "etf outflow", "spot etf", "etf flows",
    "bitcoin etf", "btc etf", "ethereum etf", "eth etf", "ibit", "fbtc",
)
_FUNDING_OI_WORDS: Final[tuple[str, ...]] = (
    "funding rate", "open interest", "liquidation", "short squeeze",
    "long squeeze", "leverage", "perpetual", "perp ", "kaldıraç", "tasfiye",
)
_EARNINGS_WORDS: Final[tuple[str, ...]] = (
    "earnings", "quarterly results", "revenue beat", "revenue miss", "eps",
    "guidance", "profit warning", "bilanço", "kâr",
)
_OUTAGE_WORDS: Final[tuple[str, ...]] = (
    "exchange outage", "halts trading", "halts withdrawals", "trading halted",
    "system outage", "downtime", "hack", "exploit", "breach", "insolvency",
    "withdrawals frozen", "borsa kesintisi", "çekim durdu", "saldırıya uğradı",
)


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def classify_event_type(title: str) -> CatalystEventType:
    """Başlığı deterministik event_type'a eşler (ilk eşleşen öncelikli).

    Sıralama önemlidir: outage/rumor en güvenlik-kritik olduğu için önce; makro
    veri olayları jeopolitikten önce (örtüşmeyi netleştirmek için)."""
    t = title.lower()
    # Güvenlik-kritik / veri-kalitesi olayları önce.
    if _has(t, _OUTAGE_WORDS):
        return "exchange_outage"
    if _has(t, _INFLATION_WORDS):
        return "inflation_data"
    if _has(t, _JOBS_WORDS):
        return "jobs_data"
    if _has(t, _CENTRAL_BANK_WORDS):
        return "central_bank"
    if _has(t, _ETF_FLOW_WORDS):
        return "crypto_etf_flow"
    if _has(t, _FUNDING_OI_WORDS):
        return "funding_oi_squeeze"
    if _has(t, _OIL_SUPPLY_WORDS):
        return "oil_supply"
    if _has(t, _OIL_INVENTORY_WORDS):
        return "oil_inventory"
    # Jeopolitik: de-escalation escalation'dan önce (ateşkes "war" kelimesi de
    # taşıyabilir; barış sinyali öncelikli).
    if _has(t, _DEESCALATION_WORDS):
        return "geopolitical_deescalation"
    if _has(t, _ESCALATION_WORDS):
        return "geopolitical_escalation"
    if _has(t, _EARNINGS_WORDS):
        return "earnings"
    return "unknown"


def is_rumor(title: str) -> bool:
    return _has(title.lower(), _RUMOR_WORDS)


# ---------------------------------------------------------------------------
# event_type → half-life kuralları.
#   half_life_min        : yarı-ömür (dk); valid_until = ts + half_life × 3
#   timeframes           : etkilenen timeframe'ler (yarı-ömür mantığı)
#   default_assets       : event_type'ın klasik etkilediği semboller
#   base_action          : taban actionability (surprise ile yükseltilebilir)
#   bias_kind            : bağlam yön türetme stratejisi (yalnızca sunum)
# ---------------------------------------------------------------------------

_RULES: Final[dict[CatalystEventType, dict]] = {
    # Ateşkes → risk-premium unwind (Brent ↓, altın hedge unwind), risk-on (BTC).
    # Kısa yarı-ömür: 15m/1h whipsaw, 4h confirmation, 1d regime watch.
    "geopolitical_deescalation": {
        "half_life_min": 90,
        "timeframes": ["15m", "1h", "4h"],
        "default_assets": ["BRENT", "XAUUSD", "BTCUSD", "ETHUSD", "VIX"],
        "base_action": "CAUTION",
        "bias_kind": "risk_on",
    },
    # Eskalasyon → risk-off, enerji risk primi; daha geniş ve dayanıklı.
    "geopolitical_escalation": {
        "half_life_min": 150,
        "timeframes": ["15m", "1h", "4h", "1d"],
        "default_assets": ["BRENT", "XAUUSD", "VIX", "BTCUSD", "ETHUSD"],
        "base_action": "CAUTION",
        "bias_kind": "risk_off",
    },
    # CPI/PCE → ilk 15m/1h whipsaw (watch only); 1h/4h confirmation; 1d regime.
    "inflation_data": {
        "half_life_min": 90,
        "timeframes": ["15m", "1h", "4h"],
        "default_assets": ["DXY", "XAUUSD", "BTCUSD", "US10Y"],
        "base_action": "CAUTION",
        "bias_kind": "sentiment",
    },
    # NFP/jobs → CPI'ye benzer whipsaw.
    "jobs_data": {
        "half_life_min": 90,
        "timeframes": ["15m", "1h", "4h"],
        "default_assets": ["DXY", "XAUUSD", "BTCUSD", "US10Y"],
        "base_action": "CAUTION",
        "bias_kind": "sentiment",
    },
    # FOMC → 15m/1h watch only, 4h/1d meaningful; uzun yarı-ömür.
    "central_bank": {
        "half_life_min": 240,
        "timeframes": ["15m", "1h", "4h", "1d"],
        "default_assets": ["DXY", "XAUUSD", "BTCUSD", "US10Y", "VIX"],
        "base_action": "CAUTION",
        "bias_kind": "sentiment",
    },
    # OPEC → Brent 15m/1h/4h.
    "oil_supply": {
        "half_life_min": 180,
        "timeframes": ["15m", "1h", "4h"],
        "default_assets": ["BRENT"],
        "base_action": "WATCH",
        "bias_kind": "sentiment",
    },
    # EIA → Brent 15m/1h.
    "oil_inventory": {
        "half_life_min": 120,
        "timeframes": ["15m", "1h"],
        "default_assets": ["BRENT"],
        "base_action": "WATCH",
        "bias_kind": "sentiment",
    },
    # ETF flow → crypto 1h/4h/1d.
    "crypto_etf_flow": {
        "half_life_min": 180,
        "timeframes": ["1h", "4h", "1d"],
        "default_assets": ["BTCUSD", "ETHUSD"],
        "base_action": "WATCH",
        "bias_kind": "sentiment",
    },
    # Funding/OI squeeze → crypto 15m/1h (hızlı).
    "funding_oi_squeeze": {
        "half_life_min": 60,
        "timeframes": ["15m", "1h"],
        "default_assets": ["BTCUSD", "ETHUSD"],
        "base_action": "CAUTION",
        "bias_kind": "contrarian",
    },
    # Earnings → ilgili hisse/endeks; bizim evrende doğrudan sembol yok →
    # yalnızca bağlam (default asset boş → karar zincirine girmez).
    "earnings": {
        "half_life_min": 240,
        "timeframes": ["1h", "4h", "1d"],
        "default_assets": [],
        "base_action": "WATCH",
        "bias_kind": "sentiment",
    },
    # Exchange outage → DQS/freshness riski; en kısıtlayıcı.
    "exchange_outage": {
        "half_life_min": 120,
        "timeframes": ["15m", "1h", "4h"],
        "default_assets": ["BTCUSD", "ETHUSD"],
        "base_action": "NO_POSITION_INCREASE",
        "bias_kind": "none",
    },
    # Rumor → yalnızca bağlam (verified=False zorunlu, trade'e dönüşmez).
    "rumor_unverified": {
        "half_life_min": 45,
        "timeframes": ["15m", "1h"],
        "default_assets": [],
        "base_action": "CONTEXT_ONLY",
        "bias_kind": "none",
    },
    "unknown": {
        "half_life_min": 30,
        "timeframes": ["15m"],
        "default_assets": [],
        "base_action": "CONTEXT_ONLY",
        "bias_kind": "none",
    },
}

_ACTION_RANK: Final[dict[CatalystActionability, int]] = {
    "CONTEXT_ONLY": 0,
    "WATCH": 1,
    "CAUTION": 2,
    "NO_POSITION_INCREASE": 3,
}

# Şiddet (intensity) kelimeleri → surprise büyüklüğü.
_INTENSITY_WORDS: Final[tuple[str, ...]] = (
    "surprise", "unexpected", "shock", "stunning", "sharp", "soars", "plunges",
    "record", "biggest", "historic", "massive", "spike", "collapse", "crash",
    "sürpriz", "beklenmedik", "şok", "rekor",
)
_BEAT_WORDS: Final[tuple[str, ...]] = ("beat", "beats", "tops", "above forecast", "hotter")
_MISS_WORDS: Final[tuple[str, ...]] = ("miss", "misses", "below forecast", "cooler", "softer")


def _surprise_level(title: str, sentiment: Direction | None) -> float:
    """İşaretli sürpriz seviyesi (-1..+1). İşaret = piyasa yönü, |.| = şiddet.

    Deterministik: sentiment tabanı (±0.3) + intensity (→0.7) + beat/miss (→0.9)."""
    t = title.lower()
    sign = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}.get(sentiment or "neutral", 0.0)
    if _has(t, _BEAT_WORDS):
        sign = 1.0
    elif _has(t, _MISS_WORDS):
        sign = -1.0
    if sign == 0.0:
        return 0.0
    mag = 0.3
    if _has(t, _INTENSITY_WORDS):
        mag = 0.7
    if _has(t, _BEAT_WORDS) or _has(t, _MISS_WORDS):
        mag = max(mag, 0.9)
    return round(sign * mag, 3)


def _bias(kind: str, sentiment: Direction | None, surprise: float) -> Direction:
    """Bağlam yön türetme (yalnızca sunum; gate yön bağımsızdır)."""
    if kind == "risk_on":
        return "bullish"
    if kind == "risk_off":
        return "bearish"
    if kind == "contrarian":
        return "neutral"
    if kind == "sentiment":
        if surprise > 0:
            return "bullish"
        if surprise < 0:
            return "bearish"
        return sentiment or "neutral"
    return "neutral"


def _confidence(verified: bool, freshness: str | None, relevance: str) -> float:
    if not verified:
        return 0.2
    c = 0.5
    c += {"FRESH": 0.3, "RECENT": 0.15, "STALE": 0.0}.get(freshness or "", 0.0)
    c += {"HIGH": 0.15, "MEDIUM": 0.05, "LOW": 0.0}.get(relevance, 0.0)
    return round(min(1.0, c), 3)


def _escalate_action(base: CatalystActionability, surprise: float) -> CatalystActionability:
    """Yüksek sürpriz tabanı yükseltebilir (asla düşürmez)."""
    if abs(surprise) >= 0.7 and base == "CAUTION":
        return "NO_POSITION_INCREASE"
    if abs(surprise) >= 0.5 and base == "WATCH":
        return "CAUTION"
    return base


def build_impact(
    headline: NewsHeadline,
    *,
    now: datetime | None = None,
) -> CatalystImpact:
    """Tek başlıktan deterministik CatalystImpact üretir (network YOK).

    Kurallar:
    - Rumor → event_type=rumor_unverified, verified=False (trade'e dönüşmez).
    - affected_assets = event_type defaultları ∪ başlıktan tespit edilen semboller.
    - valid_until = ts + half_life × 3 (≈ 3 yarı-ömür → ~%12.5 kalan etki).
    - actionability yalnızca kısıtlayıcı; surprise yüksekse yükseltilir.
    """
    ref = now or utcnow()
    title = headline.title
    rumor = is_rumor(title)
    event_type: CatalystEventType = "rumor_unverified" if rumor else classify_event_type(title)
    rule = _RULES[event_type]

    sentiment = headline.sentiment
    surprise = _surprise_level(title, sentiment)
    # Rumor / unknown asla doğrulanmaz (söylenti trade'e dönüşmez).
    verified = bool(headline.verified) and event_type not in ("rumor_unverified",)

    # affected_assets: event_type defaultları + başlıktan tespit edilen semboller.
    detected = list(classify.classify_asset_impact(title, sentiment or "neutral").keys())
    assets: list[str] = []
    for sym in [*rule["default_assets"], *detected]:
        if sym not in assets:
            assets.append(sym)

    timeframes: list[Timeframe] = list(rule["timeframes"])
    base_action: CatalystActionability = rule["base_action"]
    action = _escalate_action(base_action, surprise) if verified else "CONTEXT_ONLY"
    bias_dir = _bias(rule["bias_kind"], sentiment, surprise)
    timeframe_bias: dict[Timeframe, Direction] = {tf: bias_dir for tf in timeframes}

    half_life = int(rule["half_life_min"])
    valid_until = headline.ts + timedelta(minutes=half_life * 3)
    relevance = classify.classify_relevance(classify.classify_tags(title))

    evidence: list[str] = [
        f"event_type={event_type}",
        f"yarı-ömür ≈ {half_life}dk · valid_until {valid_until.isoformat()}",
    ]
    if surprise:
        evidence.append(f"surprise {surprise:+.2f}")
    if rumor:
        evidence.append("rumor: doğrulanmamış → yalnızca bağlam (trade yok)")
    elif now is not None and ref > valid_until:
        evidence.append("yarı-ömür doldu → yalnızca bağlam")

    return CatalystImpact(
        catalyst_id=f"cat::{headline.id}",
        headline_id=headline.id,
        event_type=event_type,
        surprise_level=surprise,
        affected_assets=assets,
        expected_half_life_minutes=half_life,
        affected_timeframes=timeframes,
        timeframe_bias=timeframe_bias,
        valid_until=valid_until,
        decay_curve="exponential",
        confidence=_confidence(verified, headline.freshness, relevance),
        actionability=action,
        verified=verified,
        source=headline.source,
        region=headline.region,
        freshness=headline.freshness,
        ts=headline.ts,
        evidence=evidence,
    )


def build_impacts(
    headlines: list[NewsHeadline],
    *,
    now: datetime | None = None,
    limit: int = 12,
) -> list[CatalystImpact]:
    """Başlık listesinden catalyst etkilerini üretir, en kısıtlayıcı önce.

    Aynı (event_type, affected_assets) için tek catalyst (gürültüyü azalt)."""
    impacts = [build_impact(h, now=now) for h in headlines]

    seen: set[tuple] = set()
    deduped: list[CatalystImpact] = []
    for imp in impacts:
        key = (imp.event_type, tuple(sorted(imp.affected_assets)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(imp)

    deduped.sort(
        key=lambda i: (
            -_ACTION_RANK[i.actionability],
            0 if i.verified else 1,
            -i.ts.timestamp(),
        )
    )
    return deduped[:limit]
