"""Learning özetini paper state'ten üretir — API endpoint'i bunu döndürür."""
from __future__ import annotations

from dataclasses import asdict

from packages.data.registry.loader import active_weights_version
from packages.learning import outcomes as outcomes_mod
from packages.learning import rebalance_store, run_store
from packages.learning.calibration import reliability_bins
from packages.learning.walkforward import summarize as wf_summarize
from packages.paper import state as paper_state

# UX1 — Sharpe / win-rate gibi metrikler bu eşiğin altında istatistiksel
# olarak anlamlı değildir; frontend bunları büyük göstermez (LearningPanel
# "INSUFFICIENT SAMPLE" uyarısı). Frontend hesap yapmaz: karar backend'de.
MIN_RELIABLE_TRADES = 20


def _proposal_status() -> str:
    """Rebalance proposal durumu (additive yüzey) — PENDING/APPROVED/REJECTED/NONE."""
    cur = rebalance_store.get_pending()
    return str(cur.get("status")) if cur else "NONE"


def build_summary() -> dict:
    s = paper_state.load()
    # B4 — başlık metrikleri de canonical outcome birleşiminden (recent_trades +
    # decision_log) türetilir. Eskiden yalnız `recent_trades` (volatile ~200
    # pencere) okunuyordu; bu yüzden başlık 12 trade gösterirken alt kırılımlar
    # 55 gösterip ÇELİŞİYORDU. Artık tek kaynak: outcomes_from_state.
    outcomes = outcomes_mod.outcomes_from_state(s)
    total = len(outcomes)
    wins = sum(1 for o in outcomes if o.pnl > 0)
    losses = sum(1 for o in outcomes if o.pnl < 0)
    breakeven = total - wins - losses
    # F1-2 — win_rate paydası kararlı trade'ler (wins+losses); başabaş
    # (time-stop BE çıkışı gibi) win_rate'i suni düşürmez, ayrı sayılır.
    decided = wins + losses
    win_rate = round(wins / decided, 3) if decided else 0.0

    pnls = [o.pnl for o in outcomes]
    sharpe = None
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = var**0.5 if var > 0 else 0.0
        sharpe = round((mean / sd) * (252**0.5), 3) if sd > 0 else 0.0

    # G6: gerçek predicted_confidence (verified outcome'lardan). Placeholder
    # 0.5 baseline'ı kaldırıldı — DATA_POLICY: verified+predicted'a sahip
    # outcome'lar örneklere alınır. /learning/calibration endpoint'i ile aynı
    # kaynak → panel ile başlık tutarlı.
    samples = [
        (float(o.predicted_confidence), o.pnl > 0)
        for o in outcomes
        if o.data_verified and o.predicted_confidence is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]

    wf = wf_summarize(pnls)
    walk = asdict(wf) if wf else None

    # L1 — timeframe-aware breakdown'lar (aynı canonical outcome listesinden).
    # 15m outcome 1d bucket'ını ETKİLEMEZ (her bucket ayrı).
    bd = outcomes_mod.breakdowns(outcomes)
    verified_outcomes = sum(1 for o in outcomes if o.data_verified)

    # F1-1 — R-bazlı expectancy (boyut-bağımsız edge): yalnız r_multiple taşıyan
    # outcome'lar (legacy/SL'siz girmez). USD metrikleri olduğu gibi sürer.
    r_vals = [o.r_multiple for o in outcomes if o.r_multiple is not None]
    expectancy_r = round(sum(r_vals) / len(r_vals), 4) if r_vals else None

    return {
        "total_trades": total,
        "breakeven_trades": breakeven,  # F1-2 additive — BE görünür, loss değil
        "expectancy_r": expectancy_r,   # F1-1 additive — R-katı ortalama
        "r_sample": len(r_vals),        # F1-1 additive — R hesaplanabilen outcome sayısı
        "min_sample": MIN_RELIABLE_TRADES,
        "sample_sufficient": total >= MIN_RELIABLE_TRADES,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "sortino": sharpe,
        "max_dd_pct": round(
            max(0.0, (s.peak_equity_usd - s.equity_usd) / s.peak_equity_usd)
            if s.peak_equity_usd > 0
            else 0.0,
            4,
        ),
        "walk_forward": walk,
        "calibration": bins,
        "module_skew": {},
        # Aktif manifest'ten (approve sonrası güncellenir) — eskiden "1.0.0"
        # sabit kodluydu ve owner'a yanlış aktif versiyon gösteriyordu.
        "weights_version": active_weights_version(),
        # --- L1 additive (frontend hesap yapmaz; backend türetir) ---
        "outcomes_total": len(outcomes),
        "verified_outcomes": verified_outcomes,
        "by_timeframe": bd["by_timeframe"],
        "by_symbol": bd["by_symbol"],
        "by_regime": bd["by_regime"],
        "by_dominant_module": bd["by_dominant_module"],
        "by_close_reason": bd["by_close_reason"],
        # F1-3 additive — modül katkı vektörü attribution'u (kazanan vs kaybeden
        # trade'lerdeki ortalama katkı). Salt gözlem; F3 regresyonunun ham yüzeyi.
        "module_attribution": outcomes_mod.module_attribution(outcomes),
        "worker_last_run": run_store.load(),
        "proposal_status": _proposal_status(),
    }
