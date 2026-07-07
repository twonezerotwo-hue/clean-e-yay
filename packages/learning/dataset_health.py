"""CP1 — Öğrenme veri-hazırlık (coverage / readiness) raporu.

Soru: "öğrenme adı altında biriktirdiğimiz veri her öğrenici için YETERLİ mi,
yoksa atıl mı duruyor?" Bu modül o boşluğu kapatır — yeni veri TOPLAMAZ, yeni
kaynak EKLEMEZ; yalnızca mevcut canonical outcome'lar ([[outcomes]]) üzerinden
kapsama (verified/confidence/excursion yüzdeleri) + öğrenici-başı hazırlık
(yeterli örnek var mı) türetir.

build_summary zaten total/verified/breakdown veriyor; bu onu TEKRARLAMAZ, üstüne
"yakıt hazır mı" sentezini ekler (eşikler trainer'ların TEK kaynağından okunur).

PAPER_SAFE / observe-only — karar zincirine etkisi yoktur.
"""
from __future__ import annotations

from packages.learning import calibration_store
from packages.learning import outcomes as outcomes_mod
from packages.learning.summary import MIN_RELIABLE_TRADES


def report(outcomes: list | None = None) -> dict:
    """Veri-hazırlık özeti. `outcomes` verilmezse canlı state'ten türetilir
    (recent_trades + decision_log birleşimi — outcomes_from_state)."""
    outs = outcomes if outcomes is not None else outcomes_mod.outcomes_from_state()
    total = len(outs)
    verified = sum(1 for o in outs if o.data_verified)
    with_conf = sum(1 for o in outs if o.predicted_confidence is not None)
    with_excursion = sum(1 for o in outs if (o.mae_pct or 0.0) > 0 or (o.mfe_pct or 0.0) > 0)
    # Çıkış Otopsisi $ tahmininin güvenilirliği: size_usd olan outcome oranı.
    # Düşükse forensics'in dolar rakamları çoğunlukla notional-çıkarım vekiliyle
    # geliyor demektir (denetim 2026-07-03, E-serisi görünürlük tamamlayıcısı).
    with_size = sum(1 for o in outs if getattr(o, "size_usd", None) is not None)
    # Kalibrasyonun gerçek yakıtı: verified VE açılışta güven damgası olan outcome.
    trainable = sum(1 for o in outs if o.data_verified and o.predicted_confidence is not None)

    def _pct(n: int) -> float:
        return round(n / total, 3) if total else 0.0

    # Y-2 — üçlü-bariyer etiket dağılımı (exit_forensics.barrier_label tek kaynak;
    # burada yeniden sınıflandırma YOK). "Şanslı artı" (time-stop lucky_win) ile
    # "hakiki kazanç" (TP clean_win) ve "korunamayan kâr" (roundtrip) ayrışır —
    # Y-5 meta-label eğitim etiketinin veri hazırlığı buradan izlenir.
    from packages.learning import exit_forensics  # lazy: dairesel import yok
    by_barrier: dict[str, int] = {}
    by_quality: dict[str, int] = {}
    for o in outs:
        try:
            lbl = exit_forensics.barrier_label(o)
        except Exception:  # tek bozuk kayıt dağılımı düşürmesin
            continue
        by_barrier[lbl["barrier"]] = by_barrier.get(lbl["barrier"], 0) + 1
        by_quality[lbl["quality"]] = by_quality.get(lbl["quality"], 0) + 1

    # Öğrenici-başı hazırlık — eşikler trainer'ların kendi sabitlerinden (tek kaynak).
    learners = [
        {
            "name": "calibration",
            "have": trainable,
            "need": calibration_store.MIN_SAMPLES,
            "ready": trainable >= calibration_store.MIN_SAMPLES,
        },
        {
            "name": "weights_metrics",
            "have": verified,
            "need": MIN_RELIABLE_TRADES,
            "ready": verified >= MIN_RELIABLE_TRADES,
        },
    ]
    return {
        "total": total,
        "verified": verified,
        "trainable": trainable,
        "coverage": {
            "verified_pct": _pct(verified),
            "confidence_pct": _pct(with_conf),
            "excursion_pct": _pct(with_excursion),
            "size_usd_pct": _pct(with_size),
        },
        "learners": learners,
        "all_ready": all(item["ready"] for item in learners),
        # Y-2 additive — mevcut alanlar dokunulmadı; panel bu bloğu okur.
        "barrier_labels": {
            "by_barrier": dict(sorted(by_barrier.items())),
            "by_quality": dict(sorted(by_quality.items())),
        },
    }
