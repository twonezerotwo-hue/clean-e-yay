"""Phase 2 — deterministic paper execution simulation (mark-to-market + fills).

The single, formalized source of the paper account's price->PnL arithmetic:
mark-to-market (unrealized) PnL, realized fill PnL, and SL/TP fill triggers. The
lifecycle owns orchestration (status transitions, audit, time-stop timing, price
sanity) and delegates the numbers here.

Fill model (preserved from lifecycle): a protective level fills at the *observed
tick price*, not at the SL/TP level — a conservative paper assumption. SL is checked
before TP.

PAPER_SAFE / NO_EXECUTION. This module ONLY computes. Every input is passed in
explicitly (primitives) — there is no PaperState/Position parameter, so it cannot
open, close, resize, or mutate a trade. It never touches a broker, never reads
live/network data, and places no orders. A "fill" here is a simulated paper fill
price, never a real execution.
"""
from __future__ import annotations

from dataclasses import dataclass

# Exit reasons produced by a *price-triggered* fill. Time-stop / kill-switch exits
# are timing/risk concerns owned by lifecycle; their PnL still routes through
# realized_pnl below, so the fill arithmetic stays single-sourced.
SL_HIT = "SL_HIT"
TP_HIT = "TP_HIT"


def unrealized_pnl(
    side: str, entry_price: float, current_price: float, size_usd: float
) -> float:
    """Mark-to-market PnL (USD) of an open position at `current_price`. Pure.

    Same formula the realized fill uses, evaluated at the current mark.
    """
    move = (
        (current_price - entry_price)
        if side == "long"
        else (entry_price - current_price)
    )
    return move / entry_price * size_usd


def realized_pnl(
    side: str, entry_price: float, exit_price: float, size_usd: float
) -> float:
    """Realized PnL (USD) of a paper fill at `exit_price`. Pure."""
    return unrealized_pnl(side, entry_price, exit_price, size_usd)


def triggered_exit(
    side: str, sl: float | None, tp: float | None, price: float
) -> str | None:
    """Which protective level `price` fills, if any — SL checked before TP
    (preserves lifecycle ordering). Returns SL_HIT / TP_HIT / None. Pure."""
    if sl is not None and (
        (side == "long" and price <= sl) or (side == "short" and price >= sl)
    ):
        return SL_HIT
    if tp is not None and (
        (side == "long" and price >= tp) or (side == "short" and price <= tp)
    ):
        return TP_HIT
    return None


@dataclass(frozen=True)
class Fill:
    """A simulated paper fill: reason, fill price, realized PnL. A frozen value
    object — producing one opens/closes nothing and mutates nothing."""

    reason: str
    fill_price: float
    pnl_usd: float


def simulate_exit_fill(
    *,
    side: str,
    entry_price: float,
    sl: float | None,
    tp: float | None,
    size_usd: float,
    price: float,
) -> Fill | None:
    """If `price` triggers SL/TP, return the simulated Fill (filled at the observed
    price); else None. Pure — no side effects, no state, no orders."""
    reason = triggered_exit(side, sl, tp, price)
    if reason is None:
        return None
    return Fill(
        reason=reason,
        fill_price=price,
        pnl_usd=realized_pnl(side, entry_price, price, size_usd),
    )


__all__ = [
    "SL_HIT",
    "TP_HIT",
    "Fill",
    "realized_pnl",
    "simulate_exit_fill",
    "triggered_exit",
    "unrealized_pnl",
]
