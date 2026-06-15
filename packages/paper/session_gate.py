"""Apply a market-session decision to a paper-open candidate (restrictive-only).

This is the *paper-layer* adapter: it asks packages/market_sessions (pure) for a
session decision and turns it into a routing instruction the open flow applies.
Market sessions never open/close trades themselves — this module does the routing
and only ever RESTRICTS (block / manual_ready / size clamp ≤ 1.0). RiskGate stays
final and is evaluated separately upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from packages import market_sessions
from packages.market_sessions.models import (
    AssetSessionContext,
    MarketSessionDecision,
    MarketSessionDecisionInput,
)


@dataclass(frozen=True)
class SessionGate:
    decision: MarketSessionDecision
    route: str  # "open" | "manual_ready" | "block"
    effective_multiplier: float  # ≤ 1.0 — multiply base size_multiplier by this
    reason_code: str | None
    phase: str
    primary_market_open: bool | None

    def attribution(self) -> dict:
        """Fields stamped onto the opened position (decision-log attribution)."""
        return {
            "open_session_action": self.decision.action,
            "open_session_phase": self.phase,
            "open_session_reason": self.decision.reason_code or self.decision.reason,
            "open_session_size_multiplier": self.effective_multiplier,
            "open_session_primary_market_open": self.primary_market_open,
            "open_session_evidence": "; ".join(self.decision.evidence) or None,
        }


def _primary_phase(ctx: AssetSessionContext) -> str:
    if not ctx.relevant_markets:
        return "unknown"
    for preferred in ("opening_window", "closing_window"):
        for s in ctx.relevant_markets:
            if s.session_phase == preferred:
                return preferred
    for s in ctx.relevant_markets:
        if s.is_open:
            return s.session_phase
    return ctx.relevant_markets[0].session_phase


def evaluate_open(
    symbol: str,
    side: str,
    timeframe: str,
    *,
    now_utc: datetime,
    regime: str | None = None,
    risk_action: str | None = None,
) -> SessionGate:
    cfg = market_sessions.load_config()
    ctx = market_sessions.asset_context(symbol, now_utc, cfg)
    decision = market_sessions.evaluate(
        MarketSessionDecisionInput(
            asset_code=symbol,
            now_utc=now_utc,
            candidate_side=side,
            candidate_timeframe=timeframe,
            regime=regime,
            risk_gate_status=risk_action,
        ),
        cfg,
    )
    effective = min(1.0, max(0.0, decision.size_multiplier))
    if decision.action == "block":
        route = "block"
    elif decision.action == "manual_ready":
        route = "manual_ready"
    else:  # allow / caution → open (caution only restricts size; RiskGate is final)
        route = "open"
    return SessionGate(
        decision=decision,
        route=route,
        effective_multiplier=effective,
        reason_code=decision.reason_code,
        phase=_primary_phase(ctx),
        primary_market_open=ctx.primary_market_open,
    )
