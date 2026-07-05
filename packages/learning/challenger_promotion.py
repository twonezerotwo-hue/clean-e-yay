"""B-4 — Challenger ağırlık terfi kriteri (owner ÖNERİ paketi; KIRMIZI ÇİZGİ).

Amaç (owner kararı 2026-07-05): B-3'ün rejim başına ürettiği CHALLENGER ağırlık
setleri, aynı geçmiş kararlarda (backtest_challenger kayıtları) champion (canlı
aktif) ağırlıklara karşı EŞLEŞMELİ kıyaslanır. Challenger, ayrışma isabetinde
istatistiksel olarak öne geçerse governor defterine OWNER ONAY PAKETİ sunulur.

EŞLEŞMELİ KIYAS (drift yok — champion matematiği REUSE):
- Her kayıtta modül SKORLARI B-2 üretiminde canlı `consensus.build()` ile
  yeniden kuruldu (aktif champion ağırlıklarıyla). Burada aynı skorları alıp
  İKİ ağırlık vektörüyle yeniden harmanlarız — champion (aktif) vs challenger
  (B-3). Harman + yön `consensus._redistribute` / `consensus._direction`'ın
  KENDİSİDİR (kopya yok): fark YALNIZ ağırlık vektöründedir, matematik aynı.
- Piyasa gerçeği = ham `forward_return` işareti (nötr ölü-bant `_MARKET_FLAT_BAND`
  altında YÖNSÜZ → çözülmez). Bir kayıt ayrışma sayılır ANCAK champion ve
  challenger farklı yön verir VE piyasa kararlı yönde hareket ederse; kazanan
  yönü tutandır (missed_opportunity semantiği: challenger haklı=challenger_win,
  champion haklı=champion_win). İkisi de tutmazsa (nötr vs ters) çözülmez.

ÜÇ KRİTER (promotion_criteria ile aynı ruh, ağırlık kanalı):
  1. Eşleşmiş karar hacmi ≥ min_matched_decisions.
  2. Çözülmüş ayrışma ≥ min_resolved_disagreements.
  3. Challenger ayrışma isabetinin %95 Wilson ALT sınırı > 0.5 (şans değil).

KIRMIZI ÇİZGİ (Anayasa/CP5): kriter TUTSA BİLE hiçbir ağırlık otomatik terfi
etmez. READY paketi STRATEGY_ENABLE governor önerisidir; onay bile YALNIZ defteri
günceller — canlı ağırlık/config DEĞİŞMEZ. Terfinin kendisi owner'ın elle
yürüteceği ayrı iştir (mevcut owner-gated rebalance yolu).

PAPER_SAFE / NO_EXECUTION — yalnız okur, yeniden-harmanlar, sayar, paket üretir.
"""
from __future__ import annotations

from datetime import UTC, datetime

from packages.consensus.engine import _direction, _redistribute
from packages.data.registry.loader import load_active_weights, load_thresholds
from packages.learning import backtest_recon, challenger_trainer
from packages.learning import promotion_rail as rail
from packages.learning.backtest_recon import _FLAT_BAND as _MARKET_FLAT_BAND

_DEFAULTS = {
    "min_matched_decisions": 200,
    "min_resolved_disagreements": 30,
}


def cfg() -> dict:
    try:
        raw = load_thresholds().get("challenger_weight_promotion") or {}
        return {
            "min_matched_decisions": max(
                1,
                int(raw.get("min_matched_decisions", _DEFAULTS["min_matched_decisions"])),
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


def _bands() -> tuple[float, float]:
    """Yön bandı (bullish_min/bearish_max) — consensus ile TEK kaynak."""
    try:
        cons = load_thresholds().get("consensus", {})
        return float(cons.get("bullish_min", 55.0)), float(cons.get("bearish_max", 45.0))
    except (OSError, KeyError, ValueError, TypeError):
        return 55.0, 45.0


def _scores(rec: dict) -> dict[str, float]:
    """Kaydın yeniden-kurulan modül skorları (ağırlıktan BAĞIMSIZ girdi)."""
    contribs = rec.get("module_contributions") or {}
    return {
        name: float(c["score"])
        for name, c in contribs.items()
        if isinstance(c, dict) and c.get("score") is not None
    }


def _blend_direction(
    scores: dict[str, float], weights: dict, bull: float, bear: float
) -> str | None:
    """Modül skorlarını bir ağırlık vektörüyle harmanla → yön. `consensus`'un
    KENDİ `_redistribute`/`_direction`'ı (mevcut modüller üzerinde normalize):
    champion ve challenger AYNI matematik, fark yalnız ağırlık vektörü."""
    if not scores:
        return None
    w = _redistribute(weights, set(scores))
    weighted = sum(scores[name] * w.get(name, 0.0) for name in scores)
    final = max(0.0, min(100.0, weighted))
    return _direction(final, bull, bear)


def _market_dir(forward_return, band: float) -> str | None:
    """Piyasa gerçeği: ham forward-return işareti. |fr| ≤ band → YÖNSÜZ (None)."""
    if forward_return is None:
        return None
    fr = float(forward_return)
    if fr > band:
        return "up"
    if fr < -band:
        return "down"
    return None


def _matches(direction: str | None, market: str) -> bool:
    return (direction == "bullish" and market == "up") or (
        direction == "bearish" and market == "down"
    )


def _resolve(champ_dir: str | None, chal_dir: str | None, market: str | None) -> str | None:
    """Ayrışmayı çöz. Aynı yön / yönsüz piyasa → None (çözülmez). Yalnız TAM BİRİ
    piyasa yönünü tutarsa kazanan (missed_win / avoided_loss analogu)."""
    if market is None or champ_dir == chal_dir:
        return None
    champ_ok = _matches(champ_dir, market)
    chal_ok = _matches(chal_dir, market)
    if chal_ok and not champ_ok:
        return "challenger_win"
    if champ_ok and not chal_ok:
        return "champion_win"
    return None  # ikisi de yönü tutmadı (nötr vs ters) → kanıt değil


def _challenger_weights_from_training(records: list[dict]) -> dict[str, dict]:
    """B-3 eğitiminden rejim başına PROPOSED challenger ağırlıkları (yalnız
    yeterli-veri rejimleri; INSUFFICIENT rejimler eşleşmeye girmez)."""
    trained = challenger_trainer.train_challenger(records) if records else {}
    return {
        reg: d["challenger_weights"]
        for reg, d in trained.items()
        if d.get("status") == "PROPOSED" and d.get("challenger_weights")
    }


def evaluate(
    *,
    records: list[dict] | None = None,
    challenger_weights: dict[str, dict] | None = None,
    champion_weights: dict[str, dict] | None = None,
) -> dict:
    """Eşleşmeli terfi değerlendirmesi. Üretim: tümü None → gerçek kaynaklar.

    `records` None → `backtest_recon.read_challenger()`. `challenger_weights` None
    → B-3 eğitiminden PROPOSED rejimler. `champion_weights` None → canlı aktif
    ağırlıklar. (Enjeksiyon yalnız test/izole kıyas için; canlıya YAZMAZ.)"""
    c = cfg()
    if records is None:
        records = backtest_recon.read_challenger()
    if challenger_weights is None:
        challenger_weights = _challenger_weights_from_training(records)
    if champion_weights is None:
        regimes_cfg = load_active_weights().get("regimes") or {}
        champion_weights = dict(regimes_cfg)
    bull, bear = _bands()

    matched = 0
    challenger_wins = 0
    champion_wins = 0
    per_regime: dict[str, dict[str, int]] = {}
    for rec in records:
        regime = str(rec.get("regime_label") or "NEUTRAL")
        chal_w = challenger_weights.get(regime)
        if not chal_w:
            continue  # bu rejimde challenger ağırlığı yok → eşleşme yok
        champ_w = champion_weights.get(regime) or champion_weights.get("NEUTRAL")
        if not champ_w:
            continue
        scores = _scores(rec)
        champ_dir = _blend_direction(scores, champ_w, bull, bear)
        chal_dir = _blend_direction(scores, chal_w, bull, bear)
        if champ_dir is None or chal_dir is None:
            continue  # skor yok → iki motor da karar veremez
        matched += 1
        pr = per_regime.setdefault(
            regime, {"matched": 0, "challenger_win": 0, "champion_win": 0}
        )
        pr["matched"] += 1
        outcome = _resolve(
            champ_dir, chal_dir, _market_dir(rec.get("forward_return"), _MARKET_FLAT_BAND)
        )
        if outcome == "challenger_win":
            challenger_wins += 1
            pr["challenger_win"] += 1
        elif outcome == "champion_win":
            champion_wins += 1
            pr["champion_win"] += 1

    n_disagreements = challenger_wins + champion_wins
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
        "per_regime": per_regime,
        "challenger_wins": challenger_wins,
        "champion_wins": champion_wins,
        "proposed_regimes": sorted(challenger_weights.keys()),
        "challenger_weights": challenger_weights,
        "config": c,
        "note": (
            "READY = owner onay paketi (governor önerisi); ağırlık terfisi "
            "otomatik yapılmaz — KIRMIZI ÇİZGİ (onay bile canlı ağırlığı değiştirmez)"
        ),
    }


def run() -> dict:
    """learning_worker giriş noktası: değerlendir; READY ise governor defterine
    owner-onay paketi sun (submit dedupe'lu — her cycle yeni kayıt ÜRETMEZ)."""
    package = evaluate()
    if package["status"] == "READY":
        ci = package["checks"]["ci_disjoint"]
        n_dis = package["challenger_wins"] + package["champion_wins"]
        submitted = rail.submit_enable(
            title="Challenger ağırlık seti terfi kriterini karşıladı (rejim-bazlı)",
            summary=(
                "Eşleşmeli backtest'te challenger ağırlıkları champion'ı geçti: "
                f"{package['challenger_wins']}/{n_dis} "
                f"ayrışma isabeti {ci['challenger_win_rate']}, %95 alt sınır "
                f"{ci['wilson_low']} > 0.5. Rejimler: {package['proposed_regimes']}. "
                "Otomatik UYGULANMAZ — sen onaylasan bile canlı ağırlık değişmez; "
                "terfi ayrı elle iştir (owner-gated rebalance). KIRMIZI ÇİZGİ."
            ),
            evidence={k: v for k, v in package.items() if k != "note"},
            # requested_change SABİT anahtar → dedupe (tek PENDING paket).
            # promotion_criteria'nın anahtarından FARKLI (ayrı kanal, çakışmaz).
            requested_change={"promote_challenger_weights_review": True},
            rollback_plan="Paket reddedilir/silinir; canlı ağırlıklar değişmemiştir.",
            source="challenger_promotion",
        )
        package["proposal_id"] = (submitted or {}).get("proposal_id")
    return package


__all__ = ["cfg", "evaluate", "run"]
