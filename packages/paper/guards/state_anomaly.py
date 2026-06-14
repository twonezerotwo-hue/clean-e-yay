"""State anomaly guard — block NEW paper opens when accounting state is absurd.

Phase 2 port from e-yay-codex `paper_trading_service._detect_state_anomaly`. If
corrupt price data already leaked into stored trades, realized_pnl / equity /
daily_pnl can balloon past the starting balance. When that happens we stop opening
NEW positions (and surface the reason), but we do NOT lock existing position
management — risk-reducing closes must stay possible.

Config (`state_anomaly`): equity_multiplier, daily_pnl_fraction. The baseline is
`paper_trading.initial_equity_usd`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.data.registry.loader import load_thresholds

if TYPE_CHECKING:
    from packages.paper.state import PaperState


@dataclass
class StateAnomaly:
    detected: bool
    reasons: list[str] = field(default_factory=list)


def detect(
    *,
    realized_pnl_usd: float,
    equity_usd: float,
    daily_pnl_usd: float,
    base: float | None = None,
) -> StateAnomaly:
    th = load_thresholds()
    if base is None:
        base = float(th["paper_trading"]["initial_equity_usd"])
    cfg = th.get("state_anomaly", {}) or {}
    mult = float(cfg.get("equity_multiplier", 3.0))
    frac = float(cfg.get("daily_pnl_fraction", 0.5))
    reasons: list[str] = []
    if base > 0:
        if abs(realized_pnl_usd) > base * mult:
            reasons.append(
                f"realized_pnl {realized_pnl_usd:,.0f} > base×{mult:g} ({base * mult:,.0f})"
            )
        if equity_usd > base * mult:
            reasons.append(
                f"equity {equity_usd:,.0f} > base×{mult:g} ({base * mult:,.0f})"
            )
        if abs(daily_pnl_usd) > base * frac:
            reasons.append(
                f"daily_pnl {daily_pnl_usd:,.0f} > base×{frac:g} ({base * frac:,.0f})"
            )
    return StateAnomaly(detected=bool(reasons), reasons=reasons)


def detect_state(state: PaperState) -> StateAnomaly:
    """Convenience over a PaperState (uses its realized/equity/daily fields)."""
    return detect(
        realized_pnl_usd=state.realized_pnl_usd,
        equity_usd=state.equity_usd,
        daily_pnl_usd=state.daily_pnl_usd,
    )
