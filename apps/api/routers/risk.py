"""GET /api/v1/risk/correlation — korelasyon matrisi + cluster exposure.
GET /api/v1/risk/halts — aktif halt + timeline + gauge metrikleri.
POST /api/v1/risk/halts/reset — owner reset (tek manuel çıkış yolu).
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from packages.data.registry import assets as asset_registry
from packages.data.registry.loader import load_thresholds
from packages.paper import state as paper_state
from packages.risk import correlation
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

router = APIRouter(tags=["risk"])


def _risk_input(ps: paper_state.PaperState) -> RiskInput:
    return RiskInput(
        dqs_score=100.0,  # halt metrikleri DQS'ten bağımsız (equity bazlı)
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )


@router.get("/risk/halts")
def get_halts() -> dict:
    ps = paper_state.load()
    state = halt_store.load()
    events = [asdict(e) for e in state.events][-halt_store.MAX_HISTORY:]
    events.reverse()  # en yeni önce
    active = [e for e in events if e["active"]]
    return {
        "halt_active": bool(active),
        "active": active,
        "timeline": events,
        "metrics": halt_store.metrics(_risk_input(ps)),
        "reset_hint": "POST /api/v1/risk/halts/reset (owner) — otomatik reset yok",
    }


@router.post("/risk/halts/reset")
def post_halts_reset() -> dict:
    cleared = halt_store.owner_reset()
    return {
        "cleared_count": len(cleared),
        "cleared": [asdict(e) for e in cleared],
    }


@router.get("/risk/correlation")
def get_correlation() -> dict:
    ps = paper_state.load()
    gates = load_thresholds()["risk_gates"]
    # Trade evreni (statik + custom) + açık pozisyon sembolleri
    symbols = sorted({*asset_registry.trade_symbols(), *(p.symbol for p in ps.open_positions)})
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
