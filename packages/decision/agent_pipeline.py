"""Agent pipeline composer (step 7) — wires steps 1–6 into one per-symbol view.

Read-only orchestration over the NEW additive technical stack:
  build_timeframe_result (T1) → technical_agent.evaluate (T2) →
  consensus.timeframe.build_consensus (T2) → agent_decision.decide (T2) →
  risk.trade_economics.evaluate_trade (T2, cost + R:R gate).

It does NOT open trades, NOT size positions, and NEVER bypasses the RiskGate: the
global risk action is applied inside `agent_decision`, and the per-trade cost + R:R
gate is a FINAL restrictive overlay — a SCOUT entry whose economics fail (bad R:R
or net edge below cost) is downgraded to WATCH, never forced through. Deterministic:
the same closed bars + risk_action yield the same decision (timestamps excepted).

Existing engines (`decision/engine.py::decide_matrix`, `consensus/engine.py`) are
NOT touched — this is a parallel, additive read surface (spec §9 step 7).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from packages.agent import technical_agent
from packages.consensus.timeframe import build_consensus
from packages.data.providers import ohlcv
from packages.data.providers.technical.timeframe import build_timeframe_result
from packages.data.types import (
    AgentDecision,
    ConsensusSnapshot,
    OHLCVBar,
    TechnicalAgentOutput,
    TechnicalTimeframeResult,
    Timeframe,
)
from packages.decision import agent_decision
from packages.risk import trade_economics

# Lowest → highest; lowest available close is the freshest spot reference.
PIPELINE_TFS: tuple[Timeframe, ...] = ("15m", "1h", "4h", "1d", "1w")


@dataclass(frozen=True)
class SymbolAgentView:
    """Composed per-symbol view of the new technical pipeline (read-only)."""

    symbol: str
    agent: TechnicalAgentOutput
    consensus: ConsensusSnapshot
    decision: AgentDecision
    economics: trade_economics.TradeEconomics | None = None


def build_symbol_view(
    symbol: str,
    per_tf: dict[Timeframe, TechnicalTimeframeResult],
    *,
    current_price: float | None,
    risk_action: str | None = None,
    tf_weights: dict[Timeframe, float] | None = None,
    econ_config: trade_economics.EconomicsConfig | None = None,
) -> SymbolAgentView:
    """Pure core: compose agent → consensus → decision → cost/R:R overlay.

    `current_price` is the prospective entry price (last close); the per-trade gate
    reads stop/target from the entry TF's `key_levels`. Missing levels → the gate
    blocks (diagnostic), so a SCOUT without defined risk never auto-enters.
    """
    agent_out = technical_agent.evaluate(symbol, per_tf)
    consensus = build_consensus(symbol, per_tf, tf_weights=tf_weights)
    decision = agent_decision.decide(symbol, consensus, risk_action=risk_action)

    economics: trade_economics.TradeEconomics | None = None
    entry_tf = decision.entry_timeframe
    if entry_tf is not None and entry_tf in per_tf:
        kl = per_tf[entry_tf].key_levels
        economics = trade_economics.evaluate_trade(
            current_price, kl.stop_reference, kl.target_reference, config=econ_config
        )
        # FINAL restrictive overlay: a SCOUT entry that fails cost/R:R is downgraded
        # to WATCH (RiskGate is final; the gate only ever restricts, never boosts).
        if decision.action == "SCOUT_ALLOWED" and not economics.allow:
            decision = decision.model_copy(
                update={
                    "action": "WATCH",
                    "size_multiplier": 0.0,
                    "reason": f"economics gate: {economics.reason} — entry not viable",
                    "blocking_agents": [
                        *decision.blocking_agents,
                        f"risk:economics:{economics.reason}",
                    ],
                }
            )

    return SymbolAgentView(
        symbol=symbol,
        agent=agent_out,
        consensus=consensus,
        decision=decision,
        economics=economics,
    )


def _spot_from_bars(bars_by_tf: dict[Timeframe, list[OHLCVBar]]) -> float | None:
    """Freshest available close (lowest TF first) — the prospective entry price."""
    for tf in PIPELINE_TFS:
        bars = bars_by_tf.get(tf)
        if bars:
            return bars[-1].close
    return None


def build_symbol_view_from_bars(
    symbol: str,
    bars_by_tf: dict[Timeframe, list[OHLCVBar]],
    *,
    risk_action: str | None = None,
    tf_weights: dict[Timeframe, float] | None = None,
    econ_config: trade_economics.EconomicsConfig | None = None,
    now: datetime | None = None,
) -> SymbolAgentView:
    """Build per-TF results from closed bars, then compose the symbol view."""
    per_tf = {
        tf: build_timeframe_result(symbol, tf, bars_by_tf.get(tf, []), now=now)
        for tf in PIPELINE_TFS
    }
    return build_symbol_view(
        symbol,
        per_tf,
        current_price=_spot_from_bars(bars_by_tf),
        risk_action=risk_action,
        tf_weights=tf_weights,
        econ_config=econ_config,
    )


def build_agent_matrix(
    symbols: list[str], *, risk_action: str | None = None
) -> list[SymbolAgentView]:
    """I/O wrapper: pull cache-backed bars per TF (no live network) and compose.

    Mirrors the existing technical/decision routers' data source (`ohlcv.get_bars`,
    already pipeline-warmed). Read-only; never mutates paper state.
    """
    views: list[SymbolAgentView] = []
    for sym in symbols:
        bars_by_tf = {tf: (ohlcv.get_bars(sym, tf) or []) for tf in PIPELINE_TFS}
        views.append(
            build_symbol_view_from_bars(sym, bars_by_tf, risk_action=risk_action)
        )
    return views


def matrix_viewmodel(
    views: list[SymbolAgentView], *, risk_action: str | None = None
) -> dict:
    """Serialize composed views into a plain dict ViewModel (frontend does no math)."""
    return {
        "risk_action": risk_action,
        "timeframes": list(PIPELINE_TFS),
        "symbols": [
            {
                "symbol": v.symbol,
                "stance": v.agent.stance,
                "consensus": v.consensus.model_dump(mode="json"),
                "decision": v.decision.model_dump(mode="json"),
                "economics": asdict(v.economics) if v.economics is not None else None,
            }
            for v in views
        ],
    }
