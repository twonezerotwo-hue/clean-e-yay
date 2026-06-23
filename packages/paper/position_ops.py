"""Owner pozisyon yönetimi — SL/TP değiştir, trailing, kısmi kapat, scale-in, flip.

Pozisyon ID veya SEMBOL ile referanslanır (sembol → o sembolün son açık pozisyonu).
PAPER_SAFE / NO_EXECUTION — gerçek broker emri yok.
"""
from __future__ import annotations

from packages.data.ingestion.pipeline import get_cached_snapshot
from packages.paper import audit as paper_audit
from packages.paper import state as paper_state
from packages.paper.lifecycle import close_position, open_position


class PositionOpError(Exception):
    def __init__(self, message: str, code: int = 409) -> None:
        super().__init__(message)
        self.code = code


def _market_price(symbol: str):
    snap = get_cached_snapshot()
    for q in snap.prices:
        if q.symbol == symbol and q.price:
            return float(q.price), snap
    return None, snap


def _resolve(state, ref: str):
    """ID tam eşleşme; yoksa sembolün SON açık pozisyonu."""
    for p in state.open_positions:
        if p.id == ref:
            return p
    sym = (ref or "").strip().upper()
    matches = [p for p in state.open_positions if p.symbol == sym]
    return matches[-1] if matches else None


def _require(state, ref):
    pos = _resolve(state, ref)
    if pos is None:
        raise PositionOpError(f"{ref} için açık pozisyon yok", 404)
    return pos


def modify_sltp(ref: str, sl: float | None = None, tp: float | None = None) -> dict:
    ps = paper_state.load()
    pos = _require(ps, ref)
    if sl is None and tp is None:
        raise PositionOpError("sl ya da tp belirt", 400)
    if sl is not None:
        pos.sl = round(float(sl), 4)
    if tp is not None:
        pos.tp = round(float(tp), 4)
    paper_audit.record("MODIFY_SLTP", position_id=pos.id, symbol=pos.symbol, reason=f"sl={pos.sl} tp={pos.tp}")
    paper_state.save(ps)
    return {"position_id": pos.id, "symbol": pos.symbol, "sl": pos.sl, "tp": pos.tp}


def set_trailing(ref: str, distance_pct: float, activate_pct: float | None = None) -> dict:
    ps = paper_state.load()
    pos = _require(ps, ref)
    if not distance_pct or distance_pct <= 0:
        raise PositionOpError("trailing mesafesi sıfırdan büyük olmalı", 400)
    price, _ = _market_price(pos.symbol)
    pos.trail_distance_pct = float(distance_pct)
    if activate_pct is not None:
        pos.trail_activate_pct = float(activate_pct)
    elif pos.trail_activate_pct is None:
        pos.trail_activate_pct = 0.01
    pos.trail_peak = price if price else (pos.current_price or pos.entry_price)
    pos.trail_active = False
    paper_audit.record("SET_TRAILING", position_id=pos.id, symbol=pos.symbol, reason=f"dist={distance_pct}")
    paper_state.save(ps)
    return {
        "position_id": pos.id, "symbol": pos.symbol,
        "trail_distance_pct": pos.trail_distance_pct, "trail_peak": pos.trail_peak,
    }


def partial_close(ref: str, fraction: float | None = None, size_usd: float | None = None) -> dict:
    ps = paper_state.load()
    pos = _require(ps, ref)
    price, _ = _market_price(pos.symbol)
    if price is None or price <= 0:
        raise PositionOpError(f"{pos.symbol} için fiyat yok — kapatılamaz")
    if size_usd is not None:
        csize = float(size_usd)
    elif fraction is not None:
        csize = pos.size_usd * float(fraction)
    else:
        raise PositionOpError("oran (ör. 0.5) ya da tutar belirt", 400)
    csize = max(0.0, min(csize, pos.size_usd))
    trade = close_position(ps, pos, exit_price=price, reason="MANUAL", close_size=csize)
    paper_state.save(ps)
    remaining = next((p.size_usd for p in ps.open_positions if p.id == pos.id), 0.0)
    return {
        "position_id": pos.id, "symbol": pos.symbol,
        "closed_usd": round(csize, 2), "pnl_usd": trade.pnl_usd,
        "remaining_usd": round(remaining, 2),
    }


def scale_in(ref: str, add_size_usd: float) -> dict:
    ps = paper_state.load()
    pos = _require(ps, ref)
    if not add_size_usd or add_size_usd <= 0:
        raise PositionOpError("eklenecek tutar sıfırdan büyük olmalı", 400)
    if add_size_usd > ps.equity_usd:
        raise PositionOpError("yetersiz bakiye")
    price, _ = _market_price(pos.symbol)
    if price is None or price <= 0:
        raise PositionOpError(f"{pos.symbol} için fiyat yok")
    old = pos.size_usd
    new = old + float(add_size_usd)
    pos.entry_price = round((old * pos.entry_price + float(add_size_usd) * price) / new, 4)
    pos.size_usd = round(new, 2)
    paper_audit.record("SCALE_IN", position_id=pos.id, symbol=pos.symbol, size=add_size_usd, price_used=price)
    paper_state.save(ps)
    return {"position_id": pos.id, "symbol": pos.symbol, "size_usd": pos.size_usd, "avg_entry": pos.entry_price}


def flip(ref: str) -> dict:
    ps = paper_state.load()
    pos = _require(ps, ref)
    price, snap = _market_price(pos.symbol)
    if price is None or price <= 0:
        raise PositionOpError(f"{pos.symbol} için fiyat yok")
    sym, size = pos.symbol, pos.size_usd
    new_side = "short" if pos.side == "long" else "long"
    trade = close_position(ps, pos, exit_price=price, reason="MANUAL")
    newpos = open_position(
        ps, symbol=sym, side=new_side, entry_price=price, size_multiplier=0.0,
        manual=True, size_usd_override=size, open_reason="owner_flip",
        snapshot_id=snap.snapshot_id,
    )
    paper_audit.record("FLIP", position_id=newpos.id, symbol=sym, side=new_side, size=size, price_used=price)
    paper_state.save(ps)
    return {
        "closed_pnl_usd": trade.pnl_usd, "new_position_id": newpos.id,
        "symbol": sym, "new_side": new_side, "size_usd": size, "entry_price": price,
    }
