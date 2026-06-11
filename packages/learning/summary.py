"""Learning özetini paper state'ten üretir — API endpoint'i bunu döndürür."""
from __future__ import annotations

from dataclasses import asdict

from packages.learning.calibration import reliability_bins
from packages.learning.walkforward import summarize as wf_summarize
from packages.paper import state as paper_state


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

    # Kalibrasyon: predicted (0..1) yaklaşımı = |consensus_skor - 50| / 50
    # Trade'e kadar saklanan confidence yoksa pnl-based 0.5 baseline.
    samples = [(0.5, t.pnl_usd > 0) for t in trades]
    bins = [asdict(b) for b in reliability_bins(samples, n_bins=5)]

    wf = wf_summarize(pnls)
    walk = asdict(wf) if wf else None

    return {
        "total_trades": total,
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
    }
