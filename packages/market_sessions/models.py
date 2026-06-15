"""Typed market-session models (decision-support, presentation-only).

These carry market-session *context*. They never open/close trades, never touch
a broker, and never duplicate RiskGate. The gating policy in engine.py can only
RESTRICT (block / manual_ready / caution + size ≤ 1.0), never expand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SessionPhase = Literal[
    "closed",
    "pre_open",
    "opening_window",
    "mid_session",
    "closing_window",
    "after_close",
    "unknown",
]
LiquidityTone = Literal["high", "normal", "thin", "closed", "unknown"]
SessionRisk = Literal["normal", "caution", "manual_review", "block", "unknown"]
SessionAction = Literal["allow", "caution", "manual_ready", "block"]


@dataclass
class MarketSessionStatus:
    market_id: str
    label: str
    exchange: str
    timezone: str
    is_open: bool
    is_holiday: bool | None
    open_time_utc: str | None
    close_time_utc: str | None
    minutes_to_open: int | None
    minutes_to_close: int | None
    session_phase: SessionPhase
    liquidity_tone: LiquidityTone
    volatility_window: bool
    holiday_verified: bool
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class AssetSessionContext:
    asset_code: str
    relevant_markets: list[MarketSessionStatus]
    any_relevant_market_open: bool
    primary_market_open: bool | None
    session_risk: SessionRisk
    reason: str
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class MarketSessionDecisionInput:
    asset_code: str
    now_utc: datetime
    candidate_side: str | None = None
    candidate_timeframe: str | None = None
    regime: str | None = None
    risk_gate_status: str | None = None


@dataclass
class MarketSessionDecision:
    action: SessionAction
    size_multiplier: float
    reason: str
    # Stable manual-ready / routing reason code (e.g. market_session_opening_window).
    reason_code: str | None = None
    evidence: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
