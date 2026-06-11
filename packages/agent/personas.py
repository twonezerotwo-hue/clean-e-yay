"""Agent persona'ları + narrative üretici — şimdilik LLM bağlantısı yok.

v2.6'da Groq/Claude adapter'ı eklenecek. O zamana kadar deterministik,
sözleşmeye uygun çıktı.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.regime.classifier import RegimeOutput
from packages.risk.engine import RiskDecision

Persona = Literal["analyst", "risk_officer", "macro_strategist"]


@dataclass
class AgentVote:
    persona: Persona
    direction: str        # bullish/bearish/neutral
    confidence: float     # 0–1
    narrative: str


def _direction_for(score: float, threshold: float = 5) -> str:
    if score >= 50 + threshold:
        return "bullish"
    if score <= 50 - threshold:
        return "bearish"
    return "neutral"


def vote_analyst(cons: ConsensusResult) -> AgentVote:
    return AgentVote(
        persona="analyst",
        direction=_direction_for(cons.score),
        confidence=round(abs(cons.score - 50) / 50, 3),
        narrative=f"{cons.symbol} consensus {cons.score:.0f}, dominant={cons.dominant_module}.",
    )


def vote_risk_officer(risk: RiskDecision) -> AgentVote:
    bias = {
        "KILL_SWITCH": "bearish",
        "RISK_REDUCE": "bearish",
        "NO_POSITION_INCREASE": "bearish",
        "WATCH": "neutral",
        "HOLD": "neutral",
        "HEDGE_INCREASE": "neutral",
    }.get(risk.action, "neutral")
    return AgentVote(
        persona="risk_officer",
        direction=bias,
        confidence=0.7 if risk.action != "HOLD" else 0.4,
        narrative=f"Risk kapısı: {risk.action} — {risk.reason}",
    )


def vote_macro_strategist(regime: RegimeOutput) -> AgentVote:
    label = regime.label
    bias = {
        "OFFENSIVE": "bullish",
        "NEUTRAL": "neutral",
        "DEFENSIVE": "bearish",
        "CRISIS": "bearish",
    }[label]
    return AgentVote(
        persona="macro_strategist",
        direction=bias,
        confidence=0.6,
        narrative=f"Makro rejim {label}.",
    )


def build_votes(
    cons: ConsensusResult, regime: RegimeOutput, risk: RiskDecision
) -> tuple[list[AgentVote], bool]:
    votes = [vote_analyst(cons), vote_risk_officer(risk), vote_macro_strategist(regime)]
    # Quorum: en az 2 vote aynı yönde
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    for v in votes:
        tally[v.direction] += 1
    quorum = max(tally.values()) >= 2
    return votes, quorum
