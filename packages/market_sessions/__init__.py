"""Global market-session intelligence (decision-support, paper-safe).

Backend owns market-session meaning. This package derives — deterministically —
which markets are open, opening, or closing, whether the moment is a
high-volatility session boundary, whether a candidate asset trades in a relevant
liquid session, and a restrictive trading-gate decision (allow / caution /
manual_ready / block, size_multiplier ≤ 1.0). It never opens/closes trades,
never calls a broker, and never duplicates RiskGate.
"""
from __future__ import annotations

from .config import MarketSessionsConfig, load_config
from .engine import (
    all_market_statuses,
    asset_context,
    evaluate,
    market_status,
)
from .models import (
    AssetSessionContext,
    MarketSessionDecision,
    MarketSessionDecisionInput,
    MarketSessionStatus,
)

__all__ = [
    "AssetSessionContext",
    "MarketSessionDecision",
    "MarketSessionDecisionInput",
    "MarketSessionStatus",
    "MarketSessionsConfig",
    "all_market_statuses",
    "asset_context",
    "evaluate",
    "load_config",
    "market_status",
]
