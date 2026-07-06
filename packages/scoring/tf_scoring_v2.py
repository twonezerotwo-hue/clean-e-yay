"""tf_scoring_v2 — TF-farkında KATMANLI yön skorlaması (İZOLE, salt-gözlem).

Owner mimarisi (2026-07-06 rapor + kritik): her TF'in ROLÜ farklı, tek "puan"
torbası YOK (eski hataya dönüş yasağı):

    1w  → SIZE_BRAKE  : yalnız boyut freni (yön/giriş üretmez)
    1d  → DIRECTION   : ana yön (bias)
    4h  → DIRECTION   : setup yönü
    1h  → MULTIPLIER  : giriş kalitesi çarpanı (YÖN ÜRETMEZ)
    15m → TRIGGER     : tetik/bekle (yön VE ağırlık ÜRETMEZ)

KANIT-CAP kuralı (owner Tablo 7) — hangi sinyalin ağırlık HAKKI var:
    EDGE (kanıtlı)     → tam ağırlık (ölçülen edge_ratio orantılı)
    aday (FLAT ama     → küçük cap (CANDIDATE_CAP); kanıt gelince yükselir
      pozitif+kararlı+
      taban geçen)
    INVERSE (ters)     → 0 (ters ölçülen sinyal yön için ASLA)
    INSUFFICIENT/diğer → 0

Ağırlıklar KODA GÖMÜLMEZ — `subsignal_scorecard` artifact'ından okunur (tek
kaynak). Karne haftalık tazelendikçe tarifler kendiliğinden güncellenir. 1d/4h
karışım oranı da SABİT DEĞİL: her TF'in kanıtlı toplam gücünden türetilir
(owner kritiği #1 — sabit 0.55/0.45 çözülen sorunu geri getirirdi).

İZOLE: canlı skora/karara/paper'a SIFIR dokunuş. Sinyaller `packages/signals`
+ momentum `sub_leans`'ten REUSE (kopya yok). LOOK-AHEAD yok (çağıran son-bara
kadar veriyi geçirir).
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

# Aday (henüz kanıtlanmamış ama umutlu) sinyalin alabileceği MAX ağırlık.
# Kanıtlı sinyal ölçülen edge_ratio'suyla girer; aday bunun altında kalır.
CANDIDATE_CAP = 0.10


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


def signal_weights(
    scorecard: dict, timeframe: str, *, include_candidates: bool = True
) -> dict[str, float]:
    """Bir TF için {sinyal: ağırlık} — KANIT-CAP kuralıyla karneden türetilir.

    EDGE → edge_ratio (kanıtlı, tam); aday (FLAT + kararlı + tabanı geçen +
    pozitif oran) → min(edge_ratio, CANDIDATE_CAP); INVERSE/INSUFFICIENT/negatif
    → 0. Karne yoksa/eksikse boş dict (dürüst: kanıt yoksa ağırlık yok).

    R2 — `include_candidates=False`: yalnız EDGE-damgalılar. Walk-forward kanıtı
    (2026-07-06): adayları yön hesabına katmak kenarı SEYRELTİYOR (harman +0.27
    < yalnız-kanıtlı +0.32). Yeni kural: YÖN yalnız kanıtlılardan; adaylar
    gözlemde kalır (karne onları ölçmeye devam eder, EDGE kazanan yükselir)."""
    per_tf = (scorecard.get("per_timeframe") or {}).get(timeframe) or {}
    signals = per_tf.get("signals") or {}
    out: dict[str, float] = {}
    for name, row in signals.items():
        verdict = row.get("verdict")
        ratio = float(row.get("edge_ratio") or 0.0)
        if verdict == "EDGE":
            out[name] = ratio                      # kanıtlı → tam
        elif (
            include_candidates
            and verdict == "FLAT"
            and ratio > 0.0
            and row.get("stable")
            and row.get("beats_baseline")
        ):
            out[name] = min(ratio, CANDIDATE_CAP)  # aday → küçük cap
        # INVERSE / INSUFFICIENT / negatif oran → ağırlık yok (0)
    return out


def direction_score(timeframe: str, leans: dict[str, float], weights: dict[str, float]) -> float | None:
    """Bir DIRECTION TF'i için ağırlıklı yön skoru (−1..+1) veya None.

    Skor = Σ(lean × weight) / Σ(weight). Kanıtlı+aday ağırlık yoksa None (o TF
    bu koşulda YÖN ÜRETMEZ — gürültüyü karara sokmaz). DIRECTION dışı TF'de None."""
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


def conviction(weights: dict[str, float]) -> float:
    """Bir TF'in toplam KANIT gücü = ağırlıkların toplamı. 1d/4h karışım oranını
    türetmek için (sabit oran YOK — owner kritiği #1)."""
    return sum(w for w in weights.values() if w > 0.0)


def blended_direction(scores: dict[str, float], convictions: dict[str, float]) -> float | None:
    """[LEGACY — yalnız A/B kıyası] DIRECTION TF skorlarının kanıt-ağırlıklı harmanı.

    Walk-forward kanıtı (2026-07-06): yumuşak harman kenarı SEYRELTİYOR (+0.27,
    taban altı); birincil kural artık `regime_directed`. Bu fonksiyon gölge
    artifact'ında `direction_blend_legacy` olarak kaydedilir → D7 yarışında iki
    tasarım gerçek veriyle kıyaslanır (ölü kod değil, kontrol grubu)."""
    num = 0.0
    den = 0.0
    for tf in DIRECTION_TFS:
        s = scores.get(tf)
        c = convictions.get(tf, 0.0)
        if s is None or c <= 0.0:
            continue
        num += s * c
        den += c
    if den <= 0.0:
        return None
    return max(-1.0, min(1.0, num / den))


# Rejim → konuşma hakkı olan DIRECTION TF'i (backtest comp_A tasarımı).
_REGIME_SPEAKER = {"UP": "1d", "DOWN": "4h"}


def regime_directed(tf_scores: dict[str, float], regime: str | None) -> float | None:
    """R2 BİRİNCİL KURAL — rejim-anahtarlı yön: mikrofonu tek doğru TF'e ver.

    Backtest kanıtı (494 pencere): UP→1d trend (+0.65%), DOWN→4h yapı (DOWN'da
    tek pozitif); anahtarlı kompozit +0.53%/%59 isabet, iki-yarı kararlı, 6/9
    sembol pozitif — yumuşak harman (+0.27) ve al-tut (+0.29) net geçildi.

    Kural: UP → yalnız 1d konuşur; DOWN → yalnız 4h konuşur. Konuşma hakkı olan
    TF kanıt üretememişse None — DİĞER TF VEKÂLET ALAMAZ (backtest böyle ölçüldü;
    vekâlet ayrı bir tasarım olurdu, kanıtsız eklenmez). Rejim bilinmiyorsa None."""
    speaker = _REGIME_SPEAKER.get(regime or "")
    if speaker is None:
        return None
    return tf_scores.get(speaker)


__all__ = [
    "CANDIDATE_CAP",
    "DIRECTION_TFS",
    "ROLE",
    "blended_direction",
    "collect_leans",
    "conviction",
    "direction_score",
    "regime_directed",
    "signal_weights",
]
