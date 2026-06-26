"""Historical Edge Engine — fuzzy-similarity geçmiş setup performansı (read-only).

`mistake_memory.py` zaten exact-fingerprint eşleşmesiyle bir historical-edge gate'i
uyguluyor ve canlı `decide_for_symbol()` zincirine bağlı (size küçültür, RiskGate'i
bypass etmez). O modüle dokunulmuyor.

Bu modül onun **tamamlayıcısı**: exact match çok dar olduğu için (her fingerprint
kombinasyonu nadiren tekrarlanır → N hep <20) fuzzy/weighted similarity ile "benzer"
geçmiş trade'leri bulur. Salt okunur bir gözlem katmanıdır:

- Hiçbir karar zincirine (decide_for_symbol/decide_matrix/agent_pipeline) bağlı
  DEĞİLDİR — paper state'i mutate etmez, trade açma/kapama kararını etkilemez.
- Yalnızca mevcut `outcomes.outcomes_from_state()` (zaten var olan kapanmış trade
  kayıtları) üzerinden okuma yapar; yeni bir veri kaynağı gerektirmez.
- Dashboard / Learning Lab için "bu setup'a benzer geçmiş trade'ler nasıl gitti"
  sorusuna cevap verir.

PAPER_SAFE / NO_EXECUTION: yalnızca okuma + türetme; emir/karar üretmez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from packages.data.registry.loader import load_thresholds
from packages.learning import fingerprint as fp
from packages.learning.outcomes import CanonicalOutcome, outcomes_from_state

# Defaults — `config/thresholds_v1.0.yaml::historical_edge` bunları override eder.
# Config eksik/bozuksa bu sabitlere düşülür (crash yok — diğer load_thresholds
# tüketicileriyle aynı defansif desen, örn. decision/engine.py::_timeframe_policy).
SIMILARITY_WEIGHTS: dict[str, float] = {
    "symbol": 0.25,
    "timeframe": 0.20,
    "regime": 0.15,
    "direction": 0.15,
    "score_bucket": 0.15,
    "confluence": 0.05,
    "dominant_module": 0.05,
}

SIMILARITY_SIMILAR_MIN = 0.70
SIMILARITY_STRONG_MIN = 0.85

MIN_SAMPLE_OBSERVE_ONLY = 20
MIN_SAMPLE_USABLE = 50
MIN_SAMPLE_STRONG = 100


def _cfg() -> dict:
    try:
        return load_thresholds().get("historical_edge") or {}
    except (OSError, KeyError, ValueError):
        return {}


def active_similarity_weights() -> dict[str, float]:
    """Config'teki ağırlıklar (varsa); değilse modül default'u."""
    weights = _cfg().get("similarity_weights")
    return dict(weights) if isinstance(weights, dict) and weights else dict(SIMILARITY_WEIGHTS)


def _similarity_similar_min() -> float:
    return float(_cfg().get("similarity_similar_min", SIMILARITY_SIMILAR_MIN))


def _similarity_strong_min() -> float:
    return float(_cfg().get("similarity_strong_min", SIMILARITY_STRONG_MIN))


def _sample_bands() -> tuple[int, int, int]:
    c = _cfg()
    return (
        int(c.get("min_sample_observe_only", MIN_SAMPLE_OBSERVE_ONLY)),
        int(c.get("min_sample_usable", MIN_SAMPLE_USABLE)),
        int(c.get("min_sample_strong", MIN_SAMPLE_STRONG)),
    )


@dataclass
class HistoricalEdgeResult:
    candidate_fingerprint: str
    similarity_threshold: float
    sample_count: int
    strong_sample_count: int
    win_rate: float
    avg_pnl: float
    edge_confidence: str  # observe_only | weak | usable | strong
    matched_trade_ids: list[str] = field(default_factory=list)


def _features(fingerprint_str: str | None, weights: dict[str, float]) -> dict[str, str | None]:
    parsed = fp.parse(fingerprint_str)
    return {k: parsed.get(k) for k in weights}


def similarity(a: str | None, b: str | None, *, weights: dict[str, float] | None = None) -> float:
    """Ağırlıklı feature eşleşmesi ∈ [0,1]. Eksik/None alan eşleşme sayılmaz.

    `weights` verilmezse config'teki (veya default) ağırlıklar okunur.
    """
    w = weights if weights is not None else active_similarity_weights()
    fa, fb = _features(a, w), _features(b, w)
    score = 0.0
    for key, weight in w.items():
        va, vb = fa.get(key), fb.get(key)
        if va is not None and va == vb:
            score += weight
    return round(score, 4)


def _confidence_band(n: int) -> str:
    observe_only, usable, strong = _sample_bands()
    if n >= strong:
        return "strong"
    if n >= usable:
        return "usable"
    if n >= observe_only:
        return "weak"
    return "observe_only"


def compute_edge(
    candidate_fingerprint: str,
    outcomes: list[CanonicalOutcome] | None = None,
    *,
    similarity_min: float | None = None,
) -> HistoricalEdgeResult:
    """Aday fingerprint'e fuzzy-benzer geçmiş trade'lerin winrate/avg_pnl özeti.

    `outcomes` verilmezse mevcut paper state'ten türetilir (read-only).
    N her zaman `similarity_min` eşiğine göre sayılır (§ N tanımı sabit);
    strong_sample_count sadece ek bilgidir, ayrı bir N tanımı değildir.
    """
    weights = active_similarity_weights()
    sim_min = similarity_min if similarity_min is not None else _similarity_similar_min()
    strong_min = _similarity_strong_min()

    rows = outcomes if outcomes is not None else outcomes_from_state()
    matched: list[CanonicalOutcome] = []
    strong_count = 0
    for o in rows:
        if not o.fingerprint:
            continue
        sim = similarity(candidate_fingerprint, o.fingerprint, weights=weights)
        if sim >= sim_min:
            matched.append(o)
            if sim >= strong_min:
                strong_count += 1

    n = len(matched)
    wins = sum(1 for o in matched if o.pnl > 0)
    win_rate = round(wins / n, 3) if n else 0.0
    avg_pnl = round(sum(o.pnl for o in matched) / n, 2) if n else 0.0

    return HistoricalEdgeResult(
        candidate_fingerprint=candidate_fingerprint,
        similarity_threshold=sim_min,
        sample_count=n,
        strong_sample_count=strong_count,
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        edge_confidence=_confidence_band(n),
        matched_trade_ids=[o.trade_id for o in matched],
    )


def edge_to_dict(r: HistoricalEdgeResult) -> dict:
    return asdict(r)


def is_strong_negative(result: HistoricalEdgeResult) -> bool:
    """Conflict Resolver §28.1 'historical edge' sert-blok kriteri (spec §25.6).

    Yalnızca yeterli örnek varken (>= min_sample_usable) VE winrate eşiğin
    altındayken True — düşük N'de asla True dönmez (observe-only kalır).
    """
    _, usable, _ = _sample_bands()
    threshold = float(_cfg().get("strong_negative_winrate_max", 0.45))
    return result.sample_count >= usable and result.win_rate <= threshold


__all__ = [
    "HistoricalEdgeResult",
    "SIMILARITY_WEIGHTS",
    "active_similarity_weights",
    "compute_edge",
    "edge_to_dict",
    "is_strong_negative",
    "similarity",
]
