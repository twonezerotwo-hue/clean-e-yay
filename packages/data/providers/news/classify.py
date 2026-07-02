"""Kural tabanlı başlık sınıflandırma — eski Codex news/geo provider portu.

Deterministiktir: LLM yok, network yok. Sentiment piyasa perspektifinden,
asset_impact sembol → yön (-1.0 / 0.0 / +1.0) olarak üretilir.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from packages.data.types import NewsFreshness, Sentiment

# ---------------------------------------------------------------------------
# Sentiment sözlükleri (EN + TR)
# ---------------------------------------------------------------------------

_BULLISH_WORDS: Final[frozenset[str]] = frozenset({
    "surge", "rally", "rise", "soar", "climb", "gain", "jump", "record",
    "bullish", "breakout", "rebound", "recovery", "outperform",
    "strong", "growth", "expand", "beat", "beats", "upside",
    "approval", "adoption", "launch", "stimulus",
    "ceasefire", "deal", "agreement", "peace", "relief",
    "cut", "easing", "dovish", "pause", "pivot",
    "yükseliş", "artış", "toparlanma", "rekor", "güçlü", "büyüme",
    "anlaşma", "ateşkes", "teşvik", "pozitif", "olumlu", "yükseldi", "arttı",
})

_BEARISH_WORDS: Final[frozenset[str]] = frozenset({
    "crash", "fall", "plunge", "drop", "decline", "tumble",
    "sell", "loss", "down", "downgrade",
    "weak", "recession", "crisis", "collapse",
    "miss", "misses", "downside", "unemployment",
    "ban", "restrict", "fear", "warning", "concern", "inflation",
    "pressure", "sanction", "tariff", "default",
    "strike", "attack", "escalat", "tension", "conflict", "war",
    "hawkish", "hike", "tighten", "missile", "blockade", "retaliat",
    "düşüş", "çöküş", "baskı", "resesyon", "endişe", "kriz", "zayıf",
    "saldırı", "gerilim", "tırmanma", "yaptırım", "düştü", "negatif",
})

_BULLISH_PHRASES: Final[tuple[str, ...]] = (
    "risk-on", "risk on", "rate cut", "soft landing", "better-than-expected",
    "faiz indirimi", "yumuşak iniş",
)
_BEARISH_PHRASES: Final[tuple[str, ...]] = (
    "risk-off", "risk off", "rate hike", "worse-than-expected", "faiz artışı",
)


def classify_sentiment(text: str) -> Sentiment:
    lower = text.lower()
    words = set(lower.split())
    bullish = len(words & _BULLISH_WORDS)
    bearish = len(words & _BEARISH_WORDS)
    bullish += sum(1 for p in _BULLISH_PHRASES if p in lower)
    bearish += sum(1 for p in _BEARISH_PHRASES if p in lower)
    if bearish > bullish:
        return "bearish"
    if bullish > bearish:
        return "bullish"
    return "neutral"


# ---------------------------------------------------------------------------
# M1 — sentiment v2: çekim-eki normalizasyonu (owner-flag `news.sentiment_v2`,
# default KAPALI = v1 birebir). v1'in tam-kelime eşleşmesi İngilizce başlıkların
# 3. tekil çekimini ("Bitcoin rebounds…") sistematik kaçırıyordu; sözlükteki
# "escalat"/"retaliat" kök girdileri ise tam-kelime modunda HİÇ eşleşemiyordu.
# v2 aynı sözlük + aynı oylamayı kullanır; yalnız eşleşme kuralı değişir.
# ---------------------------------------------------------------------------

_PUNCT_STRIP = ".,;:!?()[]{}\"'’‘“”…"

# Kök-prefix eşleşmesi yalnız ≥6 harfli sözlük girdileri için ("escalat" →
# escalates/escalation). Kısa kelimeler ("cut", "down") prefix sayılmaz —
# "cutting"/"downtown" gibi yanlış pozitifleri engeller.
_STEM_PREFIX_MIN = 6


def _token_variants(token: str) -> set[str]:
    """Token'ın olası sözlük biçimleri — deterministik İngilizce çekim
    indirgemesi (bağımlılık yok). Token'ın kendisi her zaman dahil: kök
    halinde geçen kelimeler ve çekimli halleri listelenmiş TR kelimeler
    v1 ile aynı şekilde eşleşmeye devam eder."""
    t = token.strip(_PUNCT_STRIP)
    out = {token, t}
    if t.endswith("'s") or t.endswith("’s"):
        t = t[:-2]
        out.add(t)
    n = len(t)
    if n >= 4:
        if t.endswith("ies"):
            out.add(t[:-3] + "y")       # rallies → rally
        if t.endswith("ied"):
            out.add(t[:-3] + "y")       # rallied → rally
        if t.endswith("es"):
            out.add(t[:-2])             # crashes → crash
        if t.endswith("s"):
            out.add(t[:-1])             # rebounds → rebound
        if t.endswith("ed"):
            out.add(t[:-2])             # jumped → jump
        if t.endswith("d"):
            out.add(t[:-1])             # surged → surge
        if n >= 5 and t.endswith("ing"):
            out.add(t[:-3])             # falling → fall
            out.add(t[:-3] + "e")       # surging → surge
    out.discard("")
    return out


def _match_count_v2(lower: str, words: frozenset[str], phrases: tuple[str, ...]) -> int:
    count = 0
    for tok in set(lower.split()):
        if _token_variants(tok) & words:
            count += 1
            continue
        base = tok.strip(_PUNCT_STRIP)
        if any(len(w) >= _STEM_PREFIX_MIN and base.startswith(w) for w in words):
            count += 1
    count += sum(1 for p in phrases if p in lower)
    return count


def classify_sentiment_v2(text: str) -> Sentiment:
    """v1 ile aynı sözlük + aynı oylama; fark yalnız eşleşme kuralı:
    çekim ekleri indirgenir (rebounds→rebound) ve ≥6 harfli sözlük kökleri
    prefix olarak eşleşir (escalat→escalates)."""
    lower = text.lower()
    bullish = _match_count_v2(lower, _BULLISH_WORDS, _BULLISH_PHRASES)
    bearish = _match_count_v2(lower, _BEARISH_WORDS, _BEARISH_PHRASES)
    if bearish > bullish:
        return "bearish"
    if bullish > bearish:
        return "bullish"
    return "neutral"


def sentiment_v2_enabled() -> bool:
    """`news.sentiment_v2` owner-flag'i (default KAPALI = v1 birebir).

    Açılış ayrı tarihli owner kararıdır (config yorumuna yazılır); açılana
    kadar karar zinciri v1 okur, v2 yalnız `sentiment_v2` gözlem alanına yazılır."""
    try:
        from packages.data.registry.loader import load_thresholds

        return bool((load_thresholds().get("news") or {}).get("sentiment_v2", False))
    except Exception:
        return False  # config okunamazsa en güvenli: mevcut davranış (v1)


def classify_sentiment_active(text: str) -> Sentiment:
    """Karar zincirine giren sentiment: flag açıkken v2, kapalıyken v1 (bayt-aynı)."""
    return classify_sentiment_v2(text) if sentiment_v2_enabled() else classify_sentiment(text)


# ---------------------------------------------------------------------------
# Konu etiketleri + relevance
# ---------------------------------------------------------------------------

_CRYPTO_TAGS: Final[frozenset[str]] = frozenset({
    "bitcoin", "btc", "crypto", "ethereum", "eth", "blockchain",
    "stablecoin", "altcoin", "defi", "coinbase", "binance", "kripto",
})

_MACRO_TAGS: Final[frozenset[str]] = frozenset({
    "fed", "federal reserve", "interest rate", "inflation", "cpi", "ppi",
    "gdp", "recession", "treasury", "yield", "dollar", "dxy", "m2",
    "powell", "fomc", "monetary", "fiscal", "tariff", "trade war",
    "faiz", "enflasyon", "merkez bankası",
})

_ENERGY_TAGS: Final[frozenset[str]] = frozenset({
    "oil", "brent", "crude", "opec", "energy", "natural gas",
    "petroleum", "pipeline", "lng", "petrol", "doğalgaz", "enerji",
})

_METALS_TAGS: Final[frozenset[str]] = frozenset({
    "gold", "silver", "copper", "precious", "metals", "mining",
    "xau", "xag", "altın", "gümüş", "bakır",
})

_GEO_TAGS: Final[frozenset[str]] = frozenset({
    "war", "conflict", "sanction", "airstrike", "missile", "geopolitic",
    "ceasefire", "peace talks", "invasion", "offensive", "drone strike",
    "nato", "pentagon", "nuclear", "strait of hormuz",
    "savaş", "çatışma", "yaptırım", "ateşkes", "füze",
})


def classify_tags(text: str) -> tuple[str, ...]:
    lower = text.lower()
    tags: list[str] = []
    if any(kw in lower for kw in _GEO_TAGS):
        tags.append("geo")
    if any(kw in lower for kw in _CRYPTO_TAGS):
        tags.append("crypto")
    if any(kw in lower for kw in _MACRO_TAGS):
        tags.append("macro")
    if any(kw in lower for kw in _ENERGY_TAGS):
        tags.append("energy")
    if any(kw in lower for kw in _METALS_TAGS):
        tags.append("metals")
    return tuple(tags) if tags else ("general",)


def classify_relevance(tags: tuple[str, ...]) -> str:
    if "geo" in tags or "macro" in tags or "crypto" in tags:
        return "HIGH"
    if "energy" in tags or "metals" in tags:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Bölge sınıflandırması (geo-news parity)
# ---------------------------------------------------------------------------

REGIONS: Final[tuple[str, ...]] = (
    "USA", "Iran", "Israel", "China", "Russia", "Europe", "Middle East",
)

_REGION_KEYWORDS: Final[dict[str, frozenset[str]]] = {
    "USA": frozenset({
        "united states", "u.s.", "america", "washington", "white house",
        "congress", "senate", "pentagon", "federal reserve", "fed ",
        "trump", "treasury", "american",
    }),
    "Iran": frozenset({
        "iran", "tehran", "khamenei", "irgc", "nuclear deal", "jcpoa",
        "strait of hormuz", "iranian",
    }),
    "Israel": frozenset({
        "israel", "netanyahu", "tel aviv", "jerusalem", "idf", "israeli",
        "hamas", "hezbollah", "gaza", "west bank",
    }),
    "China": frozenset({
        "china", "beijing", "xi jinping", "pboc", "taiwan", "hong kong",
        "yuan", "renminbi", "chinese", "south china sea",
    }),
    "Russia": frozenset({
        "russia", "moscow", "putin", "kremlin", "ukraine", "kyiv",
        "russian", "gazprom", "ruble", "zelensky",
    }),
    "Europe": frozenset({
        "europe", "european", "eurozone", "euro zone", "ecb", "germany",
        "france", "britain", "london", "berlin", "lagarde", "brussels",
    }),
    "Middle East": frozenset({
        "middle east", "opec", "saudi", "gulf", "lebanon", "yemen",
        "houthi", "red sea", "qatar", "uae", "iraq", "syria",
    }),
}


def detect_region(text: str) -> str | None:
    lower = text.lower()
    scores: dict[str, int] = {}
    for region, keywords in _REGION_KEYWORDS.items():
        n = sum(1 for kw in keywords if kw in lower)
        if n:
            scores[region] = n
    if not scores:
        return None
    # Eşitlikte REGIONS sırası belirleyici (deterministik)
    best = max(scores.values())
    for region in REGIONS:
        if scores.get(region) == best:
            return region
    return None


# ---------------------------------------------------------------------------
# Asset impact — sembol → yön (-1 / 0 / +1)
# ---------------------------------------------------------------------------

_ESCALATION_WORDS: Final[tuple[str, ...]] = (
    "attack", "strike", "airstrike", "bomb", "missile", "offensive",
    "invade", "escalat", "military operation", "blockade",
    "saldırı", "füze", "tırmanma", "askeri operasyon",
)
_DEESCALATION_WORDS: Final[tuple[str, ...]] = (
    "ceasefire", "truce", "peace", "deal", "agreement", "hostage",
    "ateşkes", "barış", "anlaşma", "müzakere",
)


def _dir(sentiment: Sentiment) -> float:
    return {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}[sentiment]


def classify_asset_impact(title: str, sentiment: Sentiment) -> dict[str, float]:
    """Başlıktan etkilenen sembolleri ve yönlerini çıkarır (eski Codex kural
    setinin Clean sembol evrenine indirgenmiş portu)."""
    lower = title.lower()
    d = _dir(sentiment)
    impacts: dict[str, float] = {}

    if any(kw in lower for kw in ("gold", "xau", "altın")):
        impacts["XAUUSD"] = d
    if any(kw in lower for kw in ("silver", "xag", "gümüş")):
        impacts["XAGUSD"] = d
    if any(kw in lower for kw in ("oil", "brent", "crude", "opec", "petrol")):
        impacts["BRENT"] = d
    if any(kw in lower for kw in ("bitcoin", "btc", "crypto", "kripto")):
        impacts["BTCUSD"] = d
    if any(kw in lower for kw in ("ethereum", " eth ", "eth price")):
        impacts["ETHUSD"] = d
    if any(kw in lower for kw in ("dollar", "dxy", "usd index")):
        impacts["DXY"] = d

    # Fed / makro: hawkish (bearish haber) → DXY pozitif
    if any(kw in lower for kw in ("fed", "federal reserve", "inflation", "cpi",
                                  "ppi", "fomc", "rate hike", "rate cut",
                                  "enflasyon", "faiz")):
        impacts["DXY"] = 1.0 if sentiment == "bearish" else d

    # Jeopolitik korku → VIX yukarı
    if any(kw in lower for kw in ("war", "geopolit", "iran", "ukraine", "russia",
                                  "airstrike", "missile", "drone strike", "vix",
                                  "fear", "panic", "volatility",
                                  "savaş", "çatışma", "gerilim")):
        impacts["VIX"] = 1.0 if sentiment == "bearish" else 0.0

    # Orta Doğu eskalasyonu → enerji risk primi (sentiment'ten bağımsız)
    if any(kw in lower for kw in ("israel", "gaza", "hamas", "hezbollah",
                                  "netanyahu", "idf", "strait of hormuz",
                                  "hormuz", "red sea", "houthi",
                                  "israil", "gazze")):
        if any(kw in lower for kw in _ESCALATION_WORDS):
            impacts["BRENT"] = 1.0
        elif any(kw in lower for kw in _DEESCALATION_WORDS):
            impacts["BRENT"] = -1.0
        else:
            impacts.setdefault("BRENT", 0.0)

    # Rusya/Ukrayna → güvenli liman (altın) talebi
    if any(kw in lower for kw in ("russia", "ukraine", "kremlin", "putin",
                                  "rusya", "ukrayna")):
        impacts["XAUUSD"] = 1.0 if sentiment == "bearish" else d

    # Max 4 etki — geo hikayeler daha çok sinyal taşır (legacy parity)
    return dict(list(impacts.items())[:4])


# ---------------------------------------------------------------------------
# Tazelik
# ---------------------------------------------------------------------------

def freshness_of(published_at: datetime, now: datetime | None = None) -> NewsFreshness:
    ref = now or datetime.now(UTC)
    age_h = (ref - published_at).total_seconds() / 3600
    if age_h <= 2:
        return "FRESH"
    if age_h <= 12:
        return "RECENT"
    return "STALE"


# Alakasız haberleri direkt eleme (legacy parity)
_DROP_PATTERNS: Final[tuple[str, ...]] = (
    "social security", "retirement", "401(k)", "401k", "medicare",
    "lifestyle", "luxury", "vacation", "wedding", "celebrity",
    "horoscope", "sports", "football", "basketball", "soccer match",
    "movie review", "tv show", "netflix", "streaming service",
    "recipe", "diet", "weight loss", "skincare",
)


def is_irrelevant(title: str) -> bool:
    lower = title.lower()
    return any(p in lower for p in _DROP_PATTERNS)
