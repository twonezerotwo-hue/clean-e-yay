"""F4-3 — partial-TP shadow özeti (read-only ViewModel).

Kapanmış trade'lerdeki `ptp_r_hit` / `ptp_shadow_pnl_usd` izlerinden
"1R'de %X kapat + breakeven" stratejisinin gerçekleşen sonuçlarla
karşılaştırmasını üretir. Owner `partial_tp.enabled` aktivasyon kararını
bu kanıtla verir. PAPER_SAFE — yalnız okur, hiçbir karara bağlı değil.
"""
from __future__ import annotations

from packages.data.registry.loader import load_thresholds
from packages.paper import state as paper_state


def summary(state=None) -> dict:
    """Shadow-vs-actual karşılaştırması (yalnız DEĞERLENDİRİLEBİLİR kapanışlar:
    r-hit görmüş + gerçek partial-TP uygulanmamış tam kapanışlar).

    `uplift_usd` > 0 → partial-TP stratejisi bu kapanışlarda daha iyi
    performans gösterirdi (aktivasyon lehine kanıt)."""
    ps = state if state is not None else paper_state.load()
    trades = list(ps.recent_trades)
    closed = len(trades)
    r_hit = [t for t in trades if getattr(t, "ptp_r_hit", False)]
    evaluable = [t for t in r_hit if t.ptp_shadow_pnl_usd is not None]
    actual = round(sum(t.pnl_usd for t in evaluable), 2)
    shadow = round(sum(t.ptp_shadow_pnl_usd for t in evaluable), 2)
    try:
        cfg = load_thresholds().get("partial_tp") or {}
    except (OSError, KeyError, ValueError, TypeError):
        cfg = {}
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
        # aktivasyon kanıtının okunabilir hali (LLM'e fakt, ezber değil)
        "note": (
            "shadow>actual ise partial-TP bu kapanışlarda daha iyiydi; "
            "yeterli evaluable örnek birikmeden aktivasyon önerilmez"
        ),
    }


__all__ = ["summary"]
