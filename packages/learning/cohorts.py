"""Outcome kohort ayrımı — AUTO / MANUAL / EXCLUDED (denetim bulgusu 2026-07-03).

Sorun: learning özeti tüm outcome'ları ayrımsız topluyordu; tek bir manuel
pending emir (+$2,456) bütün sistemi kârlı gösteriyordu. Bu modül her
outcome'u üç kohorta ayırır ve kohort-bazlı istatistik üretir:

- AUTO:     fingerprint'li + data_verified — otomatik sistemin GERÇEK
            performansı; ağırlık trainer'ının kullandığı kümenin aynısı.
- MANUAL:   owner'ın açtığı işlemler (owner_manual / owner_flip /
            pending_stop_limit) — owner başarısı/sorumluluğu, auto değil.
- EXCLUDED: ne fingerprint ne owner izi taşıyan kayıtlar (test/unknown) —
            hiçbir başarı metriğine girmemeli, sadece şeffaflık için sayılır.

Salt gözlem (read-only): karar/ağırlık yoluna dokunmaz; summary.py additive
olarak gömer, dashboard ayrı kolonlarda gösterir.
"""
from __future__ import annotations

from packages.learning.outcomes import CanonicalOutcome

AUTO = "auto"
MANUAL = "manual"
EXCLUDED = "excluded"

# Owner-kaynaklı open_reason önekleri (packages/paper/manual_order.py,
# position_ops.py). pending_stop_limit: owner'ın koyduğu bekleyen emir dolmuş.
_MANUAL_OPEN_PREFIXES = ("owner", "pending", "manual")


def classify(o: CanonicalOutcome) -> str:
    """Tek outcome → kohort. Deterministik; trainer filtresiyle hizalı."""
    if o.fingerprint and o.data_verified:
        return AUTO
    reason = (o.open_reason or "").strip().lower()
    if reason.startswith(_MANUAL_OPEN_PREFIXES):
        return MANUAL
    return EXCLUDED


def _empty_stats() -> dict:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
    }


def _accumulate(stats: dict, o: CanonicalOutcome) -> None:
    stats["trades"] += 1
    stats["total_pnl"] += o.pnl
    if o.pnl > 0:
        stats["wins"] += 1
    elif o.pnl < 0:
        stats["losses"] += 1
    else:
        stats["breakeven"] += 1


def _finalize(stats: dict) -> dict:
    decided = stats["wins"] + stats["losses"]  # F1-2 deseni: BE payda dışı
    stats["win_rate"] = round(stats["wins"] / decided, 3) if decided else 0.0
    stats["total_pnl"] = round(stats["total_pnl"], 2)
    return stats


def cohort_summary(outcomes: list[CanonicalOutcome]) -> dict:
    """Kohort-bazlı istatistik bloğu (summary.py additive alanı).

    `auto.by_timeframe`: TF-bazlı auto kırılım — "1d kârlı görünüyor ama auto
    değil" yanılsamasını ekranda çürütmek için. `auto.manual_closed`: auto
    açılıp owner'ın kapattığı işlem sayısı (ayrı dürüstlük kalemi).
    """
    per: dict[str, dict] = {AUTO: _empty_stats(), MANUAL: _empty_stats(), EXCLUDED: _empty_stats()}
    auto_by_tf: dict[str, dict] = {}
    auto_manual_closed = 0
    for o in outcomes:
        cohort = classify(o)
        _accumulate(per[cohort], o)
        if cohort == AUTO:
            tf = o.timeframe or "?"
            _accumulate(auto_by_tf.setdefault(tf, _empty_stats()), o)
            if (o.close_reason or "").strip().upper() == "MANUAL":
                auto_manual_closed += 1
    for stats in per.values():
        _finalize(stats)
    per[AUTO]["by_timeframe"] = {tf: _finalize(s) for tf, s in sorted(auto_by_tf.items())}
    per[AUTO]["manual_closed"] = auto_manual_closed
    return per
