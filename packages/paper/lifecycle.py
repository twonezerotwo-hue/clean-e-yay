"""Paper trading lifecycle: open / tick (price update + SL/TP) / close."""
from __future__ import annotations

import hashlib
from datetime import date

from packages.data.registry.loader import load_thresholds
from packages.paper.state import PaperState, Position, Trade, utc_iso


def _sl_pct_for(symbol: str) -> float:
    th = load_thresholds()["paper_trading"]
    return float(th["sl_pct"].get(symbol, 0.04))


def _tp_rr() -> float:
    return float(load_thresholds()["paper_trading"]["tp_rr_ratio"])


def _max_pos_usd() -> float:
    return float(load_thresholds()["paper_trading"]["max_position_usd"])


def _new_id(symbol: str, opened_at: str) -> str:
    return hashlib.sha1(f"{symbol}|{opened_at}".encode()).hexdigest()[:10]


def _ensure_daily_anchor(state: PaperState) -> None:
    today = date.today().isoformat()
    if state.daily_anchor_date != today:
        state.daily_anchor_date = today
        state.daily_pnl_usd = 0.0


def open_position(
    state: PaperState,
    *,
    symbol: str,
    side: str,
    entry_price: float,
    size_multiplier: float,
    fingerprint: str | None = None,
    data_verified: bool = False,
) -> Position:
    sl_pct = _sl_pct_for(symbol)
    tp_pct = sl_pct * _tp_rr()
    size = min(_max_pos_usd() * max(0.0, min(1.5, size_multiplier)), _max_pos_usd() * 1.5)
    opened_at = utc_iso()
    sl = entry_price * (1 - sl_pct) if side == "long" else entry_price * (1 + sl_pct)
    tp = entry_price * (1 + tp_pct) if side == "long" else entry_price * (1 - tp_pct)
    pos = Position(
        id=_new_id(symbol, opened_at),
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        current_price=entry_price,
        size_usd=round(size, 2),
        sl=round(sl, 4),
        tp=round(tp, 4),
        opened_at=opened_at,
        fingerprint=fingerprint,
        data_verified=bool(data_verified),
    )
    state.open_positions.append(pos)
    return pos


def close_position(state: PaperState, pos: Position, *, exit_price: float, reason: str) -> Trade:
    pnl = pos.unrealized_pnl_usd if pos.current_price == exit_price else (
        (exit_price - pos.entry_price) / pos.entry_price * pos.size_usd
        if pos.side == "long"
        else (pos.entry_price - exit_price) / pos.entry_price * pos.size_usd
    )
    trade = Trade(
        id=pos.id,
        symbol=pos.symbol,
        side=pos.side,
        entry_price=pos.entry_price,
        exit_price=round(exit_price, 4),
        pnl_usd=round(pnl, 2),
        opened_at=pos.opened_at,
        closed_at=utc_iso(),
        close_reason=reason,
        fingerprint=pos.fingerprint,
        data_verified=pos.data_verified,
    )
    state.recent_trades.append(trade)
    state.open_positions = [p for p in state.open_positions if p.id != pos.id]
    state.realized_pnl_usd = round(state.realized_pnl_usd + trade.pnl_usd, 2)
    _ensure_daily_anchor(state)
    state.daily_pnl_usd = round(state.daily_pnl_usd + trade.pnl_usd, 2)
    state.equity_usd = round(state.equity_usd + trade.pnl_usd, 2)
    if state.equity_usd > state.peak_equity_usd:
        state.peak_equity_usd = state.equity_usd
    return trade


def tick(state: PaperState, prices: dict[str, float]) -> list[Trade]:
    """Pozisyon fiyatlarını günceller; SL/TP'ye değen pozisyonları kapatır."""
    closed: list[Trade] = []
    for pos in list(state.open_positions):
        price = prices.get(pos.symbol)
        if price is None:
            continue
        pos.current_price = price
        # SL/TP kontrol
        if pos.sl is not None and (
            (pos.side == "long" and price <= pos.sl)
            or (pos.side == "short" and price >= pos.sl)
        ):
            closed.append(close_position(state, pos, exit_price=price, reason="SL_HIT"))
            continue
        if pos.tp is not None and (
            (pos.side == "long" and price >= pos.tp)
            or (pos.side == "short" and price <= pos.tp)
        ):
            closed.append(close_position(state, pos, exit_price=price, reason="TP_HIT"))
    return closed


def max_drawdown_pct(state: PaperState) -> float:
    if state.peak_equity_usd <= 0:
        return 0.0
    return round(
        max(0.0, (state.peak_equity_usd - state.equity_usd) / state.peak_equity_usd),
        4,
    )
