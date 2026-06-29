"""G3 — otomatik-uygulanan ağırlıkların outcome-bazlı rollback denetimi.

learning_worker her koşuda `check_rollback()` çağırır. İzlenen (MONITORING) bir
auto-apply varsa: uygulama anından (applied_at) SONRA kapanan verified outcome'ları
toplar. Henüz ≥REBALANCE_ROLLBACK_MIN_OUTCOMES yeni outcome yoksa beklemeye devam
eder. Yeterli örnek biriktiğinde post-apply expectancy'i baseline ile karşılaştırır:

  * post < baseline  → ROLLED_BACK: manifest önceki versiyona geri alınır.
  * post ≥ baseline  → CONFIRMED: promosyon kalıcılaşır (active temizlenir).

Karar verince `active` temizlenir → bir sonraki uygun proposal yeniden otomatik
uygulanabilir (tek-değişiklik-tek-doğrulama).

PAPER_SAFE / NO_EXECUTION: yalnız manifest pointer'ını (owner-onaylı yüzeyin aynı
mekanizması) geri alır; emir üretmez.
"""
from __future__ import annotations

import os
from datetime import datetime

from packages.learning import outcomes as outcomes_mod
from packages.learning import rebalance_store, weight_autoapply_store

_MIN_OUTCOMES_DEFAULT = 15


def _min_outcomes() -> int:
    try:
        return max(1, int(os.environ.get("REBALANCE_ROLLBACK_MIN_OUTCOMES", _MIN_OUTCOMES_DEFAULT)))
    except (TypeError, ValueError):
        return _MIN_OUTCOMES_DEFAULT


def _after(closed_at: str | None, applied_at: str | None) -> bool:
    """closed_at > applied_at (ISO). Parse edilemezse güvenli False (pencereye alma)."""
    if not closed_at or not applied_at:
        return False
    try:
        return datetime.fromisoformat(closed_at) > datetime.fromisoformat(applied_at)
    except (TypeError, ValueError):
        return False


def _post_apply_metrics(applied_at: str) -> tuple[int, float]:
    """applied_at SONRASI kapanan verified outcome'ların (sayı, ortalama PnL)."""
    outs = [
        o
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and _after(o.closed_at, applied_at)
    ]
    n = len(outs)
    exp = round(sum(o.pnl for o in outs) / n, 4) if n else 0.0
    return n, exp


def check_rollback() -> dict:
    """İzlenen auto-apply'ı değerlendir. Durum: no_active | monitoring | CONFIRMED |
    ROLLED_BACK. Defensive: hata vermez biçimde tasarlandı (worker patlamasın)."""
    active = weight_autoapply_store.get_active()
    if not active:
        return {"status": "no_active"}

    need = _min_outcomes()
    post_n, post_exp = _post_apply_metrics(str(active.get("applied_at") or ""))
    if post_n < need:
        return {"status": "monitoring", "post_n": post_n, "need": need}

    baseline = float(active.get("baseline_expectancy", 0.0))
    if post_exp < baseline:
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
        }

    weight_autoapply_store.resolve_active(
        outcome="CONFIRMED", post_expectancy=post_exp, post_n=post_n
    )
    return {
        "status": "CONFIRMED",
        "post_expectancy": post_exp,
        "baseline_expectancy": baseline,
        "post_n": post_n,
        "confirmed_version": active.get("applied_version"),
    }


__all__ = ["check_rollback"]
