"""Learning özetini paper state'ten üretir — API endpoint'i bunu döndürür."""
from __future__ import annotations

from dataclasses import asdict

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
    trades = s.recent_trades
    total = len(trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    win_rate = round(wins / total, 3) if total else 0.0

    pnls = [t.pnl_usd for t in trades]
    sharpe = None
    if len(pnls) >= 2:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        sd = var**0.5 if var > 0 else 0.0
        sharpe = round((mean / sd) * (252**0.5), 3) if sd > 0 else 0.0

    # G6: gerçek predicted_confidence (verified trade'lerden). Placeholder
    # 0.5 baseline'ı kaldırıldı — DATA_POLICY: verified+predicted'a sahip
    # trade'ler örneklere alınır.
    samples = [
        (float(t.predicted_confidence), t.pnl_usd > 0)
        for t in trades
        if getattr(t, "data_verified", False)
        and getattr(t, "predicted_confidence", None) is not None
    ]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]

    wf = wf_summarize(pnls)
    walk = asdict(wf) if wf else None

    # L1 — timeframe-aware breakdown'lar (canonical outcome'lardan).
    # 15m outcome 1d bucket'ını ETKİLEMEZ (her bucket ayrı). Global metrikler
    # (win_rate/sharpe) korunur; bunlar additive.
    outcomes = outcomes_mod.outcomes_from_state(s)
    bd = outcomes_mod.breakdowns(outcomes)
    verified_outcomes = sum(1 for o in outcomes if o.data_verified)

    return {
        "total_trades": total,
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
        "weights_version": "1.0.0",
        # --- L1 additive (frontend hesap yapmaz; backend türetir) ---
        "outcomes_total": len(outcomes),
        "verified_outcomes": verified_outcomes,
        "by_timeframe": bd["by_timeframe"],
        "by_symbol": bd["by_symbol"],
        "by_regime": bd["by_regime"],
        "by_dominant_module": bd["by_dominant_module"],
        "by_close_reason": bd["by_close_reason"],
        "worker_last_run": run_store.load(),
        "proposal_status": _proposal_status(),
    }
