"""GET /api/v1/risk/correlation — korelasyon matrisi + cluster exposure."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS
from packages.data.registry.loader import load_thresholds
from packages.paper import state as paper_state
from packages.risk import correlation

router = APIRouter(tags=["risk"])


@router.get("/risk/correlation")
def get_correlation() -> dict:
    ps = paper_state.load()
    gates = load_thresholds()["risk_gates"]
    # Trade evreni (ilk 4) + açık pozisyon sembolleri
    symbols = sorted({*DEFAULT_SYMBOLS[:4], *(p.symbol for p in ps.open_positions)})
    entries = correlation.matrix(symbols)
    clusters = correlation.open_clusters(ps.open_positions, ps.equity_usd, entries)
    insufficient = sorted(
        f"{e.symbol_a}|{e.symbol_b}" for e in entries if e.source == "neutral"
    )
    return {
        "threshold": float(gates.get("correlation_threshold", 0.7)),
        "max_cluster_pct": float(gates.get("max_cluster_pct", 0.30)),
        "window_days": int(gates.get("correlation_window_days", 30)),
        "min_overlap_days": int(gates.get("correlation_min_overlap_days", 5)),
        "symbols": symbols,
        "matrix": [asdict(e) for e in entries],
        "clusters": clusters,
        "open_position_count": len(ps.open_positions),
        "equity_usd": round(ps.equity_usd, 2),
        "insufficient_pairs": insufficient,
    }
