"""F4-3 — partial-TP shadow özeti + terfi kriteri (read-only / owner-gated).

Kapanmış trade'lerdeki `ptp_r_hit` / `ptp_shadow_pnl_usd` izlerinden
"1R'de %X kapat + breakeven" stratejisinin gerçekleşen sonuçlarla
karşılaştırmasını üretir.

Faz-A (Çıkışlar 10/10 yolu): ham uplift n=2'de gürültü → aktivasyon için
İSTATİSTİKSEL hazırlık kapısı (promotion_rail REUSE, B-4/K-4 deseni):
  (1) ≥ min_evaluable değerlendirilebilir kapanış,
  (2) uplift-isabetinin (%kapanışta shadow>actual) %95 Wilson ALT sınırı > 0.5,
  (3) toplam uplift > 0.
ÜÇÜ DE tutarsa learning worker governor defterine OWNER ONAY PAKETİ sunar
(STRATEGY_ENABLE `partial_tp.enabled`, dedupe'lu). Aktivasyon OTOMATİK DEĞİL —
KIRMIZI ÇİZGİ (roadmap "owner onayıyla AÇ"); onay bile yalnız defteri günceller.
PAPER_SAFE — hiçbir karara bağlı değil.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.learning import promotion_rail as rail
from packages.paper import state as paper_state

_MIN_EVALUABLE_DEFAULT = 20


def _cfg() -> dict:
    try:
        return load_thresholds().get("partial_tp") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _evaluable(state=None) -> list:
    """r-hit görmüş + shadow-değerlendirilebilir tam kapanışlar (gerçek partial-TP
    UYGULANMAMIŞ olanlar — flag OFF iken tüm kapanışlar buraya düşer)."""
    ps = state if state is not None else paper_state.load()
    r_hit = [t for t in ps.recent_trades if getattr(t, "ptp_r_hit", False)]
    return [t for t in r_hit if t.ptp_shadow_pnl_usd is not None]


def evaluate(state=None) -> dict:
    """partial-TP aktivasyon hazırlığı (promotion_rail kapıları). READY = üç
    kapı da geçti → owner paketi üretilebilir. Kanıtsızsa NOT_READY (dürüst)."""
    cfg = _cfg()
    min_eval = int(cfg.get("promotion", {}).get("min_evaluable", _MIN_EVALUABLE_DEFAULT))
    ev = _evaluable(state)
    n = len(ev)
    # per-trade uplift: shadow PnL − gerçekleşen PnL (pozitif = partial-TP daha iyiydi)
    uplifts = [float(t.ptp_shadow_pnl_usd) - float(t.pnl_usd) for t in ev]
    wins = sum(1 for u in uplifts if u > 0)
    total_uplift = round(sum(uplifts), 2)

    checks = {
        "evaluable": rail.count_check(n, min_eval),
        "uplift_win_rate": rail.wilson_check(wins, n, rate_key="uplift_win_rate"),
        "net_positive": {"value": total_uplift, "required": "> 0",
                         "pass": total_uplift > 0},
    }
    status = rail.status_of(checks)
    return {
        "status": status,
        "evaluable_trades": n,
        "uplift_wins": wins,
        "total_uplift_usd": total_uplift,
        "checks": checks,
        "note": (
            "READY = üç kapı da geçti; owner STRATEGY_ENABLE paketi üretilir. "
            "Aktivasyon OTOMATİK DEĞİL (KIRMIZI ÇİZGİ) — kanıtsızsa NOT_READY."
        ),
    }


def summary(state=None) -> dict:
    """Shadow-vs-actual karşılaştırması + hazırlık hükmü (panel yüzeyi).

    `uplift_usd` > 0 → partial-TP stratejisi bu kapanışlarda daha iyi performans
    gösterirdi. `readiness` istatistiksel aktivasyon kapısıdır (owner buradan karar
    verir); ham uplift değil Wilson-alt-sınır bakılır."""
    ps = state if state is not None else paper_state.load()
    trades = list(ps.recent_trades)
    closed = len(trades)
    r_hit = [t for t in trades if getattr(t, "ptp_r_hit", False)]
    evaluable = [t for t in r_hit if t.ptp_shadow_pnl_usd is not None]
    actual = round(sum(t.pnl_usd for t in evaluable), 2)
    shadow = round(sum(t.ptp_shadow_pnl_usd for t in evaluable), 2)
    cfg = _cfg()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "trigger_r": cfg.get("trigger_r", 1.0),
        "close_fraction": cfg.get("close_fraction", 0.5),
        "breakeven": cfg.get("breakeven", True),
        "closed_trades": closed,
        "r_hit_trades": len(r_hit),
        "evaluable_trades": len(evaluable),
        "actual_pnl_usd": actual,
        "shadow_pnl_usd": shadow,
        "uplift_usd": round(shadow - actual, 2),
        "readiness": evaluate(ps),
        # aktivasyon kanıtının okunabilir hali (LLM'e fakt, ezber değil)
        "note": (
            "shadow>actual ise partial-TP bu kapanışlarda daha iyiydi; aktivasyon "
            "readiness.status=READY (Wilson-alt-sınır>0.5) + owner onayı ister"
        ),
    }


def run(state=None) -> dict:
    """learning_worker giriş noktası: hazırlığı değerlendir; READY ise governor
    defterine owner-onay paketi sun (dedupe'lu — her cycle yeni kayıt ÜRETMEZ)."""
    package = evaluate(state)
    if package["status"] == "READY":
        ci = package["checks"]["uplift_win_rate"]
        submitted = rail.submit_enable(
            title="Partial-TP çıkış stratejisi terfi kriterini karşıladı",
            summary=(
                "Değerlendirilebilir kapanış + toplam pozitif uplift + Wilson CI "
                f"ayrıklığı sağlandı: uplift-isabeti {ci['uplift_win_rate']}, "
                f"%95 alt sınır {ci['wilson_low']} > 0.5, toplam uplift "
                f"${package['total_uplift_usd']}. Aktivasyon OTOMATİK DEĞİL — owner "
                "inceleyip partial_tp.enabled'ı ayrı işle açar (KIRMIZI ÇİZGİ)."
            ),
            evidence={k: v for k, v in package.items() if k != "note"},
            requested_change={"partial_tp.enabled": True},
            rollback_plan=(
                "Paket reddedilir/silinir; canlı çıkış davranışı değişmemiştir "
                "(flag OFF). Açıldıktan sonra kötüleşirse flag false = anında geri."
            ),
            source="partial_tp_shadow",
        )
        package["proposal_id"] = (submitted or {}).get("proposal_id")
    return package


__all__ = ["evaluate", "run", "summary"]
