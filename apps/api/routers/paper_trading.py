"""GET /api/v1/paper-trading/state, POST /api/v1/paper-trading/tick"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter

from packages.data.ingestion.pipeline import DEFAULT_SYMBOLS, get_cached_snapshot
from packages.decision.engine import decide_matrix
from packages.paper import state as paper_state
from packages.paper.lifecycle import (
    flatten_all,
    max_drawdown_pct,
    open_position,
)
from packages.paper.lifecycle import (
    tick as price_tick,
)
from packages.risk import halt as halt_store
from packages.risk.engine import RiskInput

router = APIRouter(tags=["paper-trading"])


def _time_stop_status(p: paper_state.Position, now: datetime) -> tuple[str, int | None]:
    """UX1 — time-stop durumu backend'de; negatif geri sayım ÜRETİLMEZ.

    NONE → time-stop yok; ACTIVE → kalan saniye (>0); EXPIRED → süre geçti,
    kalan 0 (exit pending — fiyatla TIME_STOP_EXIT'te kapanır).
    """
    vu = getattr(p, "valid_until", None)
    if not vu:
        return "NONE", None
    try:
        deadline = datetime.fromisoformat(vu)
    except (ValueError, TypeError):
        return "NONE", None
    remaining = (deadline - now).total_seconds()
    if remaining <= 0:
        return "EXPIRED", 0
    return "ACTIVE", int(remaining)


def _serialize_state(ps: paper_state.PaperState) -> dict:
    now = datetime.now(UTC)
    open_pos = []
    unreal_total = 0.0
    for p in ps.open_positions:
        d = asdict(p)
        d["unrealized_pnl_usd"] = round(p.unrealized_pnl_usd, 2)
        ts_status, ts_remaining = _time_stop_status(p, now)
        d["time_stop_status"] = ts_status
        d["time_stop_seconds_remaining"] = ts_remaining
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
    # None fiyatlar lifecycle'a aktarılmaz; mock fiyat dağıtılmaz.
    prices = {q.symbol: q.price for q in snap.prices if q.price is not None}
    verified_flags = {q.symbol: q.verified for q in snap.prices}

    # Önce mevcut pozisyonları fiyatla güncelle (SL/TP)
    closed = price_tick(ps, prices)

    risk_in = RiskInput(
        dqs_score=snap.quality.score,
        equity_usd=ps.equity_usd,
        peak_equity_usd=ps.peak_equity_usd,
        daily_pnl_usd=ps.daily_pnl_usd,
        open_position_count=len(ps.open_positions),
    )

    # G5 — breach varsa halt'i persist et; KILL_SWITCH seviyesinde halt
    # aktifse mevcut pozisyonları düzleştir (KILL_SWITCH_EXIT). Sadece risk
    # azaltıcı; yeni açılışlar zaten risk engine'deki halt ile bloklanır.
    actions: list[dict] = []
    halts = halt_store.sync(risk_in)
    if any(h.level == "KILL_SWITCH" for h in halts):
        for cls in flatten_all(ps, prices):
            closed.append(cls)
        risk_in = RiskInput(
            dqs_score=snap.quality.score,
            equity_usd=ps.equity_usd,
            peak_equity_usd=ps.peak_equity_usd,
            daily_pnl_usd=ps.daily_pnl_usd,
            open_position_count=len(ps.open_positions),
        )

    # T2 — (symbol, timeframe) karar uzayı. 1w decide_matrix içinde zaten
    # paper_execution=false ile hold'a düşer; fingerprint TF segmenti taşır.
    _regime, _risk, decisions = decide_matrix(
        DEFAULT_SYMBOLS[:4], snap, risk_in, open_positions=ps.open_positions
    )

    for cls in closed:
        actions.append(
            {
                "symbol": cls.symbol,
                "action": "close",
                "reason": cls.close_reason,
                "timeframe": cls.timeframe,
            }
        )

    open_keys = {(p.symbol, p.timeframe) for p in ps.open_positions}
    for d in decisions:
        entry = {"symbol": d.symbol, "timeframe": d.timeframe}
        if d.action == "blocked":
            actions.append({**entry, "action": "blocked", "reason": d.reason})
            continue
        if d.action == "hold":
            actions.append({**entry, "action": "hold", "reason": d.reason})
            continue
        if (d.symbol, d.timeframe) in open_keys:
            actions.append({**entry, "action": "hold", "reason": "zaten açık (aynı TF)"})
            continue
        # Açma
        price = prices.get(d.symbol)
        if price is None or price <= 0:
            actions.append({**entry, "action": "blocked", "reason": "fiyat yok"})
            continue
        side = "long" if d.action == "open_long" else "short"
        open_position(
            ps,
            symbol=d.symbol,
            side=side,
            entry_price=price,
            size_multiplier=d.size_multiplier,
            fingerprint=d.fingerprint,
            data_verified=verified_flags.get(d.symbol, False),
            predicted_confidence=d.confidence,
            raw_confidence=d.raw_confidence,
            confidence_source=d.confidence_source,
            timeframe=d.timeframe,
        )
        actions.append({**entry, "action": "open", "reason": d.reason})

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
