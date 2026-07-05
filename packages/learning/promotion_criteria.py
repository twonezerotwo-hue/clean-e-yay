"""F5-2 — champion/challenger terfi kriterinin formalizasyonu.

Champion = canlı decide_matrix motoru; challenger = her tick yan yana koşan
shadow (agent) pipeline'ı. Bugüne kadar "shadow'a ne zaman güvenilir" sorusu
sezgiseldi. Bu modül kriteri SAYIYA bağlar ve tutunca OWNER ONAY PAKETİ üretir:

  1. Eşleşmiş karar hacmi: shadow log'da ≥ min_matched_decisions karşılaştırma
     (her (symbol) satırı bir eşleşmiş karar — iki motor da aynı snapshot'ı gördü).
  2. Ayrışma kanıtı: challenger'ın canlıdan FARKLI davranıp izlenen kararları
     (missed_opportunity çözümleri: missed_win=challenger haklıydı,
     avoided_loss=champion haklıydı) ≥ min_resolved_disagreements.
  3. CI ayrıklığı: challenger'ın ayrışma isabetinin %95 Wilson ALT sınırı > 0.5
     — yani "challenger'ın farklılıkları şans değil" iddiası istatistiksel.

KIRMIZI ÇİZGİ (Anayasa/CP5): kriter TUTSA BİLE hiçbir şey otomatik terfi etmez.
READY paketi governor önerisi (STRATEGY_ENABLE, owner-onaylı defter) olarak
sunulur; onay bile yalnız defteri günceller — canlı config değişmez. Terfinin
kendisi ayrı, owner'ın elle yürüteceği iştir.

PAPER_SAFE / NO_EXECUTION — yalnız okur, sayar, paket üretir.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.data.registry.loader import load_thresholds
from packages.decision import shadow
from packages.learning import missed_opportunity
from packages.learning import promotion_rail as rail

_DEFAULTS = {
    "min_matched_decisions": 200,
    "min_resolved_disagreements": 30,
}


def cfg() -> dict:
    try:
        raw = load_thresholds().get("promotion_criteria") or {}
        return {
            "min_matched_decisions": max(
                1, int(raw.get("min_matched_decisions", _DEFAULTS["min_matched_decisions"]))
            ),
            "min_resolved_disagreements": max(
                1,
                int(
                    raw.get(
                        "min_resolved_disagreements",
                        _DEFAULTS["min_resolved_disagreements"],
                    )
                ),
            ),
        }
    except (OSError, KeyError, ValueError, TypeError):
        return dict(_DEFAULTS)


def _matched_decisions(records: list[dict]) -> tuple[int, dict[str, int]]:
    """Shadow log'daki karşılaştırılmış (symbol-satırı) karar sayısı + agreement dağılımı."""
    matched = 0
    agreements: dict[str, int] = {}
    for rec in records:
        for row in rec.get("symbols") or []:
            ag = row.get("agreement")
            if not ag:
                continue
            matched += 1
            agreements[ag] = agreements.get(ag, 0) + 1
    return matched, agreements


def evaluate() -> dict:
    """Terfi kriteri değerlendirmesi (pure-ish; yalnız log okur). Owner paketi."""
    c = cfg()
    records = shadow.read_recent()
    matched, agreements = _matched_decisions(records)

    resolves = [
        e for e in missed_opportunity.read_recent()
        if e.get("event") == "resolve" and e.get("outcome") in ("missed_win", "avoided_loss")
    ]
    challenger_wins = sum(1 for e in resolves if e.get("outcome") == "missed_win")
    n_disagreements = len(resolves)

    checks = {
        "matched_decisions": rail.count_check(matched, c["min_matched_decisions"]),
        "resolved_disagreements": rail.count_check(
            n_disagreements, c["min_resolved_disagreements"]
        ),
        "ci_disjoint": rail.wilson_check(
            challenger_wins, n_disagreements, rate_key="challenger_win_rate"
        ),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": rail.status_of(checks),
        "checks": checks,
        "agreements": agreements,
        "challenger_wins": challenger_wins,
        "champion_wins": n_disagreements - challenger_wins,
        "config": c,
        # LLM/panel için fakt (ezber cümle değil): terfi otomatik DEĞİL.
        "note": (
            "READY = owner onay paketi üretilir (governor önerisi); terfi "
            "otomatik yapılmaz — KIRMIZI ÇİZGİ"
        ),
    }


def run() -> dict:
    """learning_worker giriş noktası: değerlendir; READY ise governor defterine
    owner-onay paketi sun (submit dedupe'lu — her cycle yeni kayıt ÜRETMEZ)."""
    package = evaluate()
    if package["status"] == "READY":
        ci = package["checks"]["ci_disjoint"]
        submitted = rail.submit_enable(
            title="Challenger (shadow pipeline) terfi kriterini karşıladı",
            summary=(
                "Eşleşmiş karar + ayrışma kanıtı + Wilson CI ayrıklığı sağlandı: "
                f"challenger ayrışma isabeti {ci['challenger_win_rate']}, "
                f"%95 alt sınır {ci['wilson_low']} > 0.5. Terfi OTOMATİK DEĞİL — "
                "owner inceleyip ayrı işle yürütür (KIRMIZI ÇİZGİ)."
            ),
            evidence={k: v for k, v in package.items() if k != "note"},
            # requested_change SABİT anahtar → dedupe her cycle'da ikinci kaydı
            # engeller (tek PENDING paket).
            requested_change={"promote_challenger_review": True},
            rollback_plan="Paket reddedilir/silinir; canlı motor değişmemiştir.",
            source="promotion_criteria",
        )
        package["proposal_id"] = (submitted or {}).get("proposal_id")
    return package


__all__ = ["cfg", "evaluate", "run"]
