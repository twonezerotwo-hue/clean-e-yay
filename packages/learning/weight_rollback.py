"""G3 — otomatik-uygulanan ağırlıkların outcome-bazlı rollback denetimi.

learning_worker her koşuda `check_rollback()` çağırır. İzlenen (MONITORING) bir
auto-apply varsa: uygulama anından (applied_at) SONRA **AÇILAN** (opened_at)
verified outcome'ları toplar. Ağırlık değişikliği GİRİŞ kararını (consensus →
hangi pozisyon açılır) etkiler; bu yüzden değişikliğe yalnız yeni ağırlıkla
açılmış trade'ler atfedilebilir. (Eskiden `closed_at > applied_at` kullanılıyordu
— eski ağırlıkla açılıp uygulamadan SONRA kapanan uzun-vade pozisyonları, örn.
1d/672sa time-stop, post-apply penceresini kirletiyordu.) Henüz
≥REBALANCE_ROLLBACK_MIN_OUTCOMES yeni outcome yoksa beklemeye devam eder. Yeterli
örnek biriktiğinde post-apply expectancy'i baseline ile karşılaştırır:

  * post < baseline  → ROLLED_BACK: manifest önceki versiyona geri alınır.
  * post ≥ baseline  → CONFIRMED: promosyon kalıcılaşır (active temizlenir).

Baseline, apply anında EŞLEŞTİRİLMİŞ bir pencereden gelir (bkz.
`pre_apply_expectancy`): post penceresiyle aynı boyut/recency'deki son verified
outcome'ların ortalaması — ömür-boyu ortalama değil. Böylece kıyas like-for-like
olur (piyasa rejimi/örneklem-boyu çarpıklığı azalır).

SONSUZ BEKLEME KORUMASI: izlenen apply REBALANCE_MONITOR_MAX_AGE_HOURS'tan
(default 336sa = 14 gün) eskiyse ve hâlâ yeterli örnek birikmediyse, izleme
güvenli tarafta sonuçlandırılır (kanıt yoksa known-good manifest'e geri alınır) ve
`active` temizlenir — aksi halde düşük hacimli rejimde apply süresiz MONITORING'de
takılıp tüm auto-apply hattını kilitlerdi (tek-değişiklik-tek-doğrulama).

Karar verince `active` temizlenir → bir sonraki uygun proposal yeniden otomatik
uygulanabilir.

PAPER_SAFE / NO_EXECUTION: yalnız manifest pointer'ını (owner-onaylı yüzeyin aynı
mekanizması) geri alır; emir üretmez.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from packages.learning import outcomes as outcomes_mod
from packages.learning import rebalance_store, weight_autoapply_store

_MIN_OUTCOMES_DEFAULT = 15
_MONITOR_MAX_AGE_HOURS_DEFAULT = 336.0  # 14 gün; 0 → süre koruması kapalı

# F1-1 — R-bazlı expectancy modu (owner-flag, default KAPALI = USD bayt-aynı).
# USD-expectancy pozisyon boyutuyla confound olur (15m küçük poz + 1d büyük poz
# aynı ortalamada); R-katı (pnl / açılış riski) boyut-bağımsız edge ölçer.
# AÇIKKEN yalnız r_multiple taşıyan verified outcome'lar örneğe girer (legacy/
# SL'siz dışarıda — dürüst daralma). DİKKAT: izleme penceresi ortasında mod
# DEĞİŞTİRME — baseline apply anında aynı modla yazılır; mod değişirse baseline
# ile post kıyası elmayla armut olur (yeni moda geçmeden aktif izlemeyi bitir).
_R_MODE_OFF = {"0", "false", "no", "off", ""}


def _r_mode() -> bool:
    return os.environ.get("EXPECTANCY_R_MODE", "0").strip().lower() not in _R_MODE_OFF


def _outcome_value(o) -> float | None:
    """Expectancy örneği: R-mode'da r_multiple (yoksa None → örnek dışı),
    USD-mode'da pnl (mevcut davranış birebir)."""
    if _r_mode():
        return o.r_multiple
    return o.pnl


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("REBALANCE_ROLLBACK_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _monitor_max_age_hours() -> float:
    try:
        return max(
            0.0,
            float(os.environ.get("REBALANCE_MONITOR_MAX_AGE_HOURS", _MONITOR_MAX_AGE_HOURS_DEFAULT)),
        )
    except (TypeError, ValueError):
        return _MONITOR_MAX_AGE_HOURS_DEFAULT


def _parse_dt(value: str | None) -> datetime | None:
    """ISO parse; naive damga → UTC varsay. Böylece aware (utc_iso) ile legacy/naive
    bir damga kıyaslanırken TypeError yutulup outcome sessizce DÜŞMEZ."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _after(ts: str | None, ref: str | None) -> bool:
    """ts > ref (ISO). Parse edilemezse güvenli False (pencereye alma)."""
    a, b = _parse_dt(ts), _parse_dt(ref)
    if a is None or b is None:
        return False
    return a > b


def _monitor_age_hours(applied_at: str) -> float | None:
    """İzlenen apply'ın yaşı (saat). applied_at parse edilemezse None."""
    dt = _parse_dt(applied_at)
    if dt is None:
        return None
    return (datetime.now(UTC) - dt).total_seconds() / 3600.0


def pre_apply_expectancy(window: int | None = None) -> tuple[int, float]:
    """Apply ANINDAKİ baseline: opened_at'e göre en son `window` verified outcome'un
    (sayı, ortalama PnL). `window` verilmezse rollback eşiği (_min_outcomes) kullanılır
    → baseline ile post-apply penceresi EŞLEŞTİRİLMİŞ boyut/recency olur."""
    need = window if window is not None else _min_outcomes()
    outs = [
        o
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and o.opened_at and _outcome_value(o) is not None
    ]
    outs.sort(key=lambda o: o.opened_at or "", reverse=True)
    sample = outs[:need]
    n = len(sample)
    exp = round(sum(_outcome_value(o) for o in sample) / n, 4) if n else 0.0
    return n, exp


def post_open_expectancy(since: str) -> tuple[int, float]:
    """`since` (ISO) SONRASI AÇILAN (opened_at) verified outcome'ların (sayı, ort PnL).
    Outcome'lar yalnız kapalı trade'lerden türer; opened_at>since filtresi →
    değişiklikten sonra açılmış + kapanmış (değişikliğe atfedilebilir) trade'ler.

    CP3 guard_safety kasası bunu yeniden kullanır (guard enable anından sonraki
    canlı expectancy); böylece eşleştirilmiş-pencere mantığı tek yerde kalır."""
    outs = [
        o
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and _after(o.opened_at, since) and _outcome_value(o) is not None
    ]
    n = len(outs)
    exp = round(sum(_outcome_value(o) for o in outs) / n, 4) if n else 0.0
    return n, exp


def _post_apply_metrics(applied_at: str) -> tuple[int, float]:
    """applied_at SONRASI AÇILAN verified outcome'ların (sayı, ort PnL) — G3 ağırlık
    rollback'i için `post_open_expectancy`'nin niyet-açık (intent-revealing) sarmalı."""
    return post_open_expectancy(applied_at)


def _decide(active: dict, *, post_exp: float, post_n: int, baseline: float,
            reason: str | None = None) -> dict:
    """post < baseline → ROLLED_BACK (manifest geri al); aksi CONFIRMED. Her iki
    durumda `active` temizlenir. `reason` verilirse sonuca eklenir (örn. expiry)."""
    if post_exp < baseline:
        rebalance_store.revert_to_manifest(active.get("prev_manifest"))
        weight_autoapply_store.resolve_active(
            outcome="ROLLED_BACK", post_expectancy=post_exp, post_n=post_n
        )
        out = {
            "status": "ROLLED_BACK",
            "post_expectancy": post_exp,
            "baseline_expectancy": baseline,
            "post_n": post_n,
            "reverted_to": active.get("prev_version"),
            "reverted_from": active.get("applied_version"),
        }
    else:
        weight_autoapply_store.resolve_active(
            outcome="CONFIRMED", post_expectancy=post_exp, post_n=post_n
        )
        out = {
            "status": "CONFIRMED",
            "post_expectancy": post_exp,
            "baseline_expectancy": baseline,
            "post_n": post_n,
            "confirmed_version": active.get("applied_version"),
        }
    if reason:
        out["reason"] = reason
    return out


def check_rollback() -> dict:
    """İzlenen auto-apply'ı değerlendir. Durum: no_active | monitoring | CONFIRMED |
    ROLLED_BACK. Defensive: hata vermez biçimde tasarlandı (worker patlamasın)."""
    active = weight_autoapply_store.get_active()
    if not active:
        return {"status": "no_active"}

    need = _min_outcomes()
    applied_at = str(active.get("applied_at") or "")
    post_n, post_exp = _post_apply_metrics(applied_at)
    baseline = float(active.get("baseline_expectancy", 0.0))

    if post_n < need:
        # Sonsuz bekleme koruması: izleme çok eskiyse güvenli tarafta kapat.
        max_age = _monitor_max_age_hours()
        age_h = _monitor_age_hours(applied_at)
        if max_age > 0 and age_h is not None and age_h >= max_age:
            if post_n == 0:
                # Hiç kanıt yok → known-good manifest'e dön (conservative).
                rebalance_store.revert_to_manifest(active.get("prev_manifest"))
                weight_autoapply_store.resolve_active(
                    outcome="ROLLED_BACK", post_expectancy=post_exp, post_n=post_n
                )
                return {
                    "status": "ROLLED_BACK",
                    "post_expectancy": post_exp,
                    "baseline_expectancy": baseline,
                    "post_n": post_n,
                    "reverted_to": active.get("prev_version"),
                    "reverted_from": active.get("applied_version"),
                    "reason": "monitor_expired_no_evidence",
                }
            # Kısmi kanıtla (post_n<need) karar ver — izlemeyi sonsuza taşımaktansa.
            return _decide(
                active, post_exp=post_exp, post_n=post_n, baseline=baseline,
                reason="monitor_expired_partial",
            )
        return {"status": "monitoring", "post_n": post_n, "need": need}

    return _decide(active, post_exp=post_exp, post_n=post_n, baseline=baseline)


__all__ = ["check_rollback", "post_open_expectancy", "pre_apply_expectancy"]
