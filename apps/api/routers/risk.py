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
from packages.portfolio import build_portfolio_risk
from packages.risk import correlation, stress
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput, risk_input_from_state

router = APIRouter(tags=["risk"])


def _risk_input(ps: paper_state.PaperState) -> RiskInput:
    return risk_input_from_state(ps, 100.0)  # halt metrikleri DQS'ten bağımsız (equity bazlı)


@router.get("/risk/halts")
def get_halts() -> dict:
    ps = paper_state.load()
    state = halt_store.load()
    events = [asdict(e) for e in state.events][-halt_store.MAX_HISTORY:]
    events.reverse()  # en yeni önce
    # DAILY_LOSS önceki UTC günün kaydı olarak diskte aktif kalsa bile artık
    # bugünün kapısı değildir; aynı filtreyi RiskEngine ile paylaş.
    active_ids = {e.id for e in halt_store.active_halts(state)}
    active = [e for e in events if e["active"] and e["id"] in active_ids]
    return {
        "halt_active": bool(active),
        "active": active,
        "timeline": events,
        "metrics": halt_store.metrics(_risk_input(ps)),
        "reset_hint": (
            "DAILY_LOSS UTC gün dönümünde kapanır; MAX_DRAWDOWN için "
            "POST /api/v1/risk/halts/reset (owner) gerekir"
        ),
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
        "price_min_overlap_days": int(gates.get("correlation_price_min_overlap_days", 20)),
        "symbols": symbols,
        "matrix": [asdict(e) for e in entries],
        "clusters": clusters,
        "open_position_count": len(ps.open_positions),
        "equity_usd": round(ps.equity_usd, 2),
        "insufficient_pairs": insufficient,
    }


@router.get("/risk/stress")
def get_risk_stress() -> dict:
    """Açık kitabın tarihsel stres testi ve kuyruk riski (salt rapor; limit değiştirmez)."""
    return stress.report(paper_state.load())


@router.get("/risk/portfolio")
def get_portfolio_risk() -> dict:
    """Read-only portfolio concentration and world-thesis alignment.

    This endpoint never mutates paper state and is intentionally separate from
    the RiskGate.  It gives the future cockpit a backend-owned exposure view
    without changing current execution behaviour.
    """
    ps = paper_state.load()
    return build_portfolio_risk(ps).to_dict()
