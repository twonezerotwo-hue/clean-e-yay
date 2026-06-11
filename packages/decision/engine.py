"""DecisionEngine — consensus + risk + learning'i birleştirir.

Eski projedeki üç ayrı kopuk parça (consensus_engine, agent_decision_aggregator,
agent_confidence) burada tek yerde. Çıktı: TradeDecision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_thresholds
from packages.regime.classifier import RegimeOutput, classify
from packages.risk.engine import RiskDecision, RiskInput
from packages.risk.engine import evaluate as evaluate_risk

Action = Literal["open_long", "open_short", "hold", "blocked"]


@dataclass
class TradeDecision:
    symbol: str
    action: Action
    confidence: float           # 0–1
    size_multiplier: float      # 0–1.5
    consensus: ConsensusResult
    risk: RiskDecision
    reason: str


def _regime_multiplier(label: str) -> float:
    return {"OFFENSIVE": 1.0, "NEUTRAL": 0.8, "DEFENSIVE": 0.5, "CRISIS": 0.35}.get(label, 0.5)


def decide_for_symbol(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    risk: RiskDecision,
) -> TradeDecision:
    th = load_thresholds()["consensus"]
    cons = build_consensus(symbol, snap, regime)

    # Risk hard gate'leri
    if risk.action in {"KILL_SWITCH"}:
        return TradeDecision(
            symbol=symbol,
            action="blocked",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
        )
    if risk.action in {"NO_POSITION_INCREASE", "RISK_REDUCE"}:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
        )

    # Consensus eşikleri
    if cons.score >= th["strong_bullish_min"]:
        action: Action = "open_long"
        size = 1.5
    elif cons.score >= th["bullish_min"]:
        action = "open_long"
        size = 1.0
    elif cons.score <= th["strong_bearish_max"]:
        action = "open_short"
        size = 1.5
    elif cons.score <= th["bearish_max"]:
        action = "open_short"
        size = 1.0
    else:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(abs(cons.score - 50) / 50, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason="Consensus eşiği aşılmadı",
        )

    # Confluence yoksa boyut yarıya iner
    if not cons.confluence_aligned:
        size *= 0.5

    size *= _regime_multiplier(regime.label)

    # Ham confidence: skor 50'den uzaklaştıkça artar
    raw_conf = abs(cons.score - 50) / 50
    return TradeDecision(
        symbol=symbol,
        action=action,
        confidence=round(min(0.99, raw_conf), 3),
        size_multiplier=round(size, 3),
        consensus=cons,
        risk=risk,
        reason=f"{cons.direction} signal · dominant={cons.dominant_module}",
    )


def decide_all(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    regime = classify(snap)
    risk = evaluate_risk(paper_state_input)
    decisions = [decide_for_symbol(s, snap, regime, risk) for s in symbols]
    return regime, risk, decisions
