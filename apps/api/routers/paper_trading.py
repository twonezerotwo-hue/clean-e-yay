"""GET /api/v1/paper-trading/state, POST /api/v1/paper-trading/tick"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.decision.engine import decide_all
from packages.learning.fingerprint import make as make_fingerprint
from packages.paper import state as paper_state
from packages.paper.lifecycle import (
    max_drawdown_pct,
    open_position,
)
from packages.paper.lifecycle import (
    tick as price_tick,
)
from packages.risk.engine import RiskInput

router = APIRouter(tags=["paper-trading"])


def _serialize_state(ps: paper_state.PaperState) -> dict:
    open_pos = []
    unreal_total = 0.0
    for p in ps.open_positions:
        d = asdict(p)
        d["unrealized_pnl_usd"] = round(p.unrealized_pnl_usd, 2)
        unreal_total += d["unrealized_pnl_usd"]
        open_pos.append(d)
    return {
        "equity_usd": round(ps.equity_usd, 2),
        "realized_pnl_usd": round(ps.realized_pnl_usd, 2),
        "unrealized_pnl_usd": round(unreal_total, 2),
        "max_drawdown_pct": max_drawdown_pct(ps),
        "sharpe_30d": 0.0,
        "open_positions": open_pos,
        "recent_trades": [asdict(t) for t in ps.recent_trades[-25:]],
    }


@router.get("/paper-trading/state")
def get_paper_state() -> dict:
    return _serialize_state(paper_state.load())


@router.post("/paper-trading/tick")
def post_paper_tick() -> dict:
    ps = paper_state.load()
    snap = get_cached_snapshot()
    prices = {q.symbol: q.price for q in snap.prices}

    # Önce mevcut pozisyonları fiyatla güncelle (SL/TP)
    closed = price_tick(ps, prices)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )
    regime, _risk, decisions = decide_all(DEFAULT_SYMBOLS[:4], snap, risk_in)

    actions: list[dict] = []
    for cls in closed:
        actions.append({"symbol": cls.symbol, "action": "close", "reason": cls.close_reason})

    open_symbols = {p.symbol for p in ps.open_positions}
    for d in decisions:
        if d.action == "blocked":
            actions.append({"symbol": d.symbol, "action": "blocked", "reason": d.reason})
            continue
        if d.action == "hold":
            actions.append({"symbol": d.symbol, "action": "hold", "reason": d.reason})
            continue
        if d.symbol in open_symbols:
            actions.append({"symbol": d.symbol, "action": "hold", "reason": "zaten açık"})
            continue
        # Açma
        price = prices.get(d.symbol)
        if price is None or price <= 0:
            actions.append({"symbol": d.symbol, "action": "blocked", "reason": "fiyat yok"})
            continue
        side = "long" if d.action == "open_long" else "short"
        fp = make_fingerprint(
            symbol=d.symbol,
            regime=regime.label,
            direction=d.consensus.direction,
            score=d.consensus.score,
            confluence=d.consensus.confluence_aligned,
            dominant_module=d.consensus.dominant_module,
        )
        open_position(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=price,
            size_multiplier=d.size_multiplier,
            fingerprint=fp,
        )
        actions.append({"symbol": d.symbol, "action": "open", "reason": d.reason})

    paper_state.save(ps)

    return {
        "tick_at": datetime.now(UTC).isoformat(),
        "signals_processed": len(decisions),
        "actions": actions,
    }


# Test/dev: pozisyonları sıfırla
@router.post("/paper-trading/reset")
def reset() -> dict:
    ps = paper_state._initial_state()
    # SL/TP olmadan sadece son trade ve pozisyonları temizle, equity sıfırlama:
    # gerçek "reset" davranışı için _initial_state yeterli
    paper_state.save(ps)
    return _serialize_state(ps)
