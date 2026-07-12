"""tf_scoring_v3 — v2 çekirdeği + konsey-kanıtlı revizyon (İZOLE, salt-gözlem).

Owner kararı (2026-07-12): "v2'yi yeni verilerle yeniden ağırlıklandırıp revize
et, gölge olarak sürsün, aynı anda backtest." v2'nin kanıtlanan parçaları AYNEN
korunur (reuse, kopya yok): TF rol mimarisi, kanıt-cap ağırlıklar (karneden),
rejim-anahtarlı konuşmacı (UP→1d, DOWN→4h), "kanıt yoksa yön yok" dürüstlüğü.

V2'den farklar — her biri 2026-07-12 YÜRÜYEN BACKTEST kanıtına dayanır
(9 makro sembol, 1d yürüyüş, 5g ufuk, 621 kararlı örnek, maruziyet-ağırlıklı):

1. **BAYAT-KARNE KAPISI** (yarış dersi: 59/59 kararın tamamı 6 günlük bayat
   karneyle üretilmişti ve al-tut'a yenildi; oysa aynı çekirdek 2 yıllık
   yürüyüşte +0.686%/birim ile al-tut'u (+0.418) geçiyor). Karne artifact'ı
   SCORECARD_MAX_AGE_DAYS'ten eskiyse v3 yön ÜRETMEZ (dürüst sessizlik).

2. **MAKRO-KARARLILIK KISMASI** (konsey: makro/fundamental sesi GÜÇLÜYKEN
   isabet %53.8 vs zayıfken %30.2). Backtest iki hipotezi ayrıştırdı:
   - makro-yön-UYUMU kısması: +0.549 → ÇÜRÜDÜ (v2 düzünden kötü; kurulmadı)
   - makro-KARARLILIK kısması: +0.729 → hafif pozitif → v3 kuralı BU:
     rotasyon skoru kararsız bölgedeyken (|skor−50| < DECISIVE_BAND) çağrının
     gücü MACRO_DAMP ile kısılır. ASLA büyütmez (no-boost); işaret değişmez.
   - NOT (kurulmadı): karşıt-hipotez (uyumsuzken tam maruziyet) +0.834 ile en
     iyiydi ama post-hoc/tek-pencere — ileri-veri (D7 yarışı) kanıtı olmadan
     kural yapılmaz (touche dersi: varyant-seçme = aşırı-uyum tuzağı).

İZOLE: canlı skora/karara/paper'a SIFIR dokunuş. Gölge üretici (D6) v2 ile
YAN YANA hesaplar; D7 yarış defteri tasarımları (v2/eski/al-tut/v3) gerçek
ileri veriyle kıyaslar. Terfi ancak yarış + owner onayıyla (KIRMIZI ÇİZGİ).
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.scoring import tf_scoring_v2 as v2

# Makro kararlılık bandı: rotasyon risk-on skoru (0-100) 50±band içindeyse
# makro görüş KARARSIZ sayılır → çağrı gücü kısılır.
DECISIVE_BAND = 10.0
# Kararsız makroda yön skorunun çarpanı (kısma; no-boost, işaret korunur).
MACRO_DAMP = 0.5
# Karne bundan eskiyse v3 konuşmaz (karne haftalık tazelenir; 10g tolerans).
SCORECARD_MAX_AGE_DAYS = 10.0


def macro_decisive(rotation_score: float | None) -> bool:
    """Makro görüş kararlı mı? (rotasyon skoru 50±DECISIVE_BAND dışında).
    Skor yoksa kararsız sayılır (kısma uygulanır — uydurma kararlılık yok)."""
    if rotation_score is None:
        return False
    return abs(float(rotation_score) - 50.0) >= DECISIVE_BAND


def macro_damp(direction: float | None, decisive: bool) -> float | None:
    """Makro-kararlılık kısması: kararlı → dokunma; kararsız → MACRO_DAMP.
    İşaret asla değişmez; skor asla BÜYÜMEZ (no-boost)."""
    if direction is None or decisive:
        return direction
    return direction * MACRO_DAMP


def scorecard_fresh(scorecard: dict, now: datetime | None = None,
                    max_age_days: float = SCORECARD_MAX_AGE_DAYS) -> bool:
    """Karne yaş kapısı: generated_at yok/bozuk/eski → False (v3 konuşmaz)."""
    try:
        gen = datetime.fromisoformat(str(scorecard.get("generated_at")))
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return False
    now = now or datetime.now(UTC)
    age = (now - gen).total_seconds()
    return 0 <= age <= max_age_days * 86400


def score(
    tf_scores: dict[str, float],
    regime: str | None,
    *,
    rotation_score: float | None,
    scorecard: dict,
    now: datetime | None = None,
) -> float | None:
    """v3 yön skoru: bayat-karne kapısı → v2 rejim-anahtarlı çekirdek →
    makro-kararlılık kısması. Her aşama None üretebilir (kanıt yoksa yön yok)."""
    if not scorecard_fresh(scorecard, now):
        return None
    base = v2.regime_directed(tf_scores, regime)
    if base is None:
        return None
    out = macro_damp(base, macro_decisive(rotation_score))
    return None if out is None else max(-1.0, min(1.0, out))


__all__ = [
    "DECISIVE_BAND",
    "MACRO_DAMP",
    "SCORECARD_MAX_AGE_DAYS",
    "macro_damp",
    "macro_decisive",
    "score",
    "scorecard_fresh",
]
