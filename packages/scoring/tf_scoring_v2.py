"""tf_scoring_v2 — touche_backup motoru + v4'ün motor parçaları (İZOLE hesap).

Owner kararı (2026-07-12): canlı teknik oy tf_scoring_v4 (owner birleşik
formülü); bu modül İKİ görev taşır, fazlası yok:

1. **touche_backup** — v4 çekimser kaldığında konuşan YEDEK yön motoru:
   rejim-anahtarlı, yalnız EDGE-kanıtlı sinyaller (karne artifact'ından ağırlık;
   koda gömme yok). 2026-07-06→12 arası canlı teknik oyun kendisiydi (494
   pencere backtest + 163 işlem kanıtı) — o yüzden yedek bu.
2. **v4 motor parçaları** — collect_leans (v4 base_leans girdisi),
   regime_directed (konuşmacı seçimi: v4.direction reuse eder), DIRECTION_TFS/ROLE.

Temizlik (2026-07-12): eski yarış tasarımları (aday-cap'li ağırlıklama,
yumuşak harman/conviction) SÖKÜLDÜ — yarışta al-tut'u geçemediler; sürüm
çorbası bitirildi (owner kararı: touche=v4, yedek=backup, gerisi yok).

Owner mimarisi (2026-07-06): her TF'in ROLÜ farklı, tek "puan" torbası YOK.
İZOLE: bu modül hiçbir yere yazmaz; gölge üretici hesaplar, canlı consensus
artifact üzerinden okur. Sinyaller `packages/signals` + momentum `sub_leans`'ten
REUSE (kopya yok). LOOK-AHEAD yok (çağıran son-bara kadar veriyi geçirir).
"""
from __future__ import annotations

from packages.learning.subsignal_scorecard import sub_leans
from packages.signals import (
    bollinger_fade,
    candle_rejection,
    market_structure,
    regime_gate,
    rsi_extreme,
    vwap_fade,
)

# TF rolleri (owner mimarisi). DIRECTION dışı TF'ler yön skoru ÜRETMEZ.
ROLE = {
    "1w": "SIZE_BRAKE",
    "1d": "DIRECTION",
    "4h": "DIRECTION",
    "1h": "MULTIPLIER",
    "15m": "TRIGGER",
}
DIRECTION_TFS = tuple(tf for tf, r in ROLE.items() if r == "DIRECTION")


def collect_leans(timeframe: str, bars: list) -> dict[str, float]:
    """Bir TF için tüm sinyal yön okumaları (−1..+1). `subsignal_scorecard`'ın
    ölçtüğü sinyallerle BİREBİR aynı küme + aynı fonksiyonlar (reuse) → karne
    verdict'leri bu lean'lerle 1:1 eşleşir. Yetersiz sinyal atlanır (uydurma yok)."""
    if not bars:
        return {}
    closes = [b.close for b in bars]
    leans: dict[str, float] = dict(sub_leans(closes, bars))  # trend / rsi / macd
    ms = market_structure.lean(bars)
    if ms is not None:
        leans["structure"] = ms
    rx = rsi_extreme.lean(closes)
    if rx is not None:
        leans["rsi_extreme"] = rx
    vf = vwap_fade.lean(bars, timeframe=timeframe)
    if vf is not None:
        leans["vwap_fade"] = vf
    bf = bollinger_fade.lean(closes)
    if bf is not None:
        leans["bollinger_fade"] = bf
    cr = candle_rejection.lean(bars)
    if cr is not None:
        leans["candle_rejection"] = cr
    rg = regime_gate.lean(closes)
    if rg is not None:
        leans["regime_gate"] = rg
    return leans


def signal_weights(scorecard: dict, timeframe: str) -> dict[str, float]:
    """touche_backup ağırlıkları: yalnız EDGE-damgalı sinyaller, ölçülen
    edge_ratio'larıyla (karne artifact'ından — koda gömme yok; karne haftalık
    tazelendikçe tarif kendiliğinden güncellenir).

    Walk-forward kanıtı (2026-07-06): adayları katmak kenarı SEYRELTİYOR
    (+0.27 < yalnız-kanıtlı +0.32) → aday/INVERSE/INSUFFICIENT ağırlık ALMAZ.
    Karne yoksa boş dict (dürüst: kanıt yoksa backup yön üretmez)."""
    per_tf = (scorecard.get("per_timeframe") or {}).get(timeframe) or {}
    signals = per_tf.get("signals") or {}
    out: dict[str, float] = {}
    for name, row in signals.items():
        if row.get("verdict") != "EDGE":
            continue
        ratio = float(row.get("edge_ratio") or 0.0)
        if ratio > 0.0:
            out[name] = ratio
    return out


def direction_score(timeframe: str, leans: dict[str, float], weights: dict[str, float]) -> float | None:
    """Bir DIRECTION TF'i için ağırlıklı yön skoru (−1..+1) veya None.

    Skor = Σ(lean × weight) / Σ(weight). Kanıtlı ağırlık yoksa None (o TF bu
    koşulda YÖN ÜRETMEZ — gürültüyü karara sokmaz). DIRECTION dışı TF'de None."""
    if ROLE.get(timeframe) != "DIRECTION":
        return None
    num = 0.0
    den = 0.0
    for name, w in weights.items():
        if w <= 0.0 or name not in leans:
            continue
        num += leans[name] * w
        den += w
    if den <= 0.0:
        return None
    return max(-1.0, min(1.0, num / den))


# Rejim → konuşma hakkı olan DIRECTION TF'i (backtest comp_A tasarımı).
_REGIME_SPEAKER = {"UP": "1d", "DOWN": "4h"}


def regime_directed(tf_scores: dict[str, float], regime: str | None) -> float | None:
    """Rejim-anahtarlı konuşmacı seçimi: mikrofonu tek doğru TF'e ver.

    Backtest kanıtı (494 pencere): UP→1d trend (+0.65%), DOWN→4h yapı (DOWN'da
    tek pozitif). Kural: UP → yalnız 1d konuşur; DOWN → yalnız 4h konuşur.
    Konuşma hakkı olan TF kanıt üretememişse None — DİĞER TF VEKÂLET ALAMAZ
    (backtest böyle ölçüldü). Rejim bilinmiyorsa None. v4.direction ve
    touche_backup ikisi de bunu kullanır."""
    speaker = _REGIME_SPEAKER.get(regime or "")
    if speaker is None:
        return None
    return tf_scores.get(speaker)


__all__ = [
    "DIRECTION_TFS",
    "ROLE",
    "collect_leans",
    "direction_score",
    "regime_directed",
    "signal_weights",
]
