"""Eşleştirilmiş-pencere beklenti yardımcıları (aktivasyon gözcüsü ve guard_safety için).

Eskiden burada otomatik uygulanan ağırlıkların outcome-bazlı geri alma denetimi
(check_rollback) vardı; 26 Kasım 2026'da ağırlık oto-uygulamasıyla birlikte kalktı
(REBALANCE_AUTO_APPLY hiç açılmamıştı, geri alma ağırlıklar git'te olduğu için
'owner_gated' dönüyordu). Ağırlık yalnız owner onayıyla değişir.

Pencereler opened_at'e göre: değişiklikten SONRA AÇILAN işlemler değişikliğe atfedilir.
PAPER_SAFE / NO_EXECUTION.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.learning import outcomes as outcomes_mod


def _outcome_value(o) -> float | None:
    """Beklenti örneği: maliyet sonrası USD (26 Kasım 2026, L6)."""
    return float(getattr(o, "net_pnl", o.pnl))


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


def pre_apply_expectancy(window: int) -> tuple[int, float]:
    """Apply ANINDAKİ baseline: opened_at'e göre en son `window` verified outcome'un
    (sayı, ortalama PnL); izleyici kendi pencere boyunu verir."""
    need = window
    outs = [
        o
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and not outcomes_mod.is_exploration(o)
        and not outcomes_mod.is_execution_anomaly(o)
        and o.opened_at and _outcome_value(o) is not None
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

    Aktivasyon gözcüsü ve guard_safety kasası kullanır; eşleştirilmiş-pencere
    mantığı tek yerde kalır."""
    outs = [
        o
        for o in outcomes_mod.outcomes_from_state()
        if o.data_verified and not outcomes_mod.is_exploration(o)
        and not outcomes_mod.is_execution_anomaly(o)
        and _after(o.opened_at, since) and _outcome_value(o) is not None
    ]
    n = len(outs)
    exp = round(sum(_outcome_value(o) for o in outs) / n, 4) if n else 0.0
    return n, exp


__all__ = ["post_open_expectancy", "pre_apply_expectancy"]
