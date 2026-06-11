"""DecisionEngine — consensus + risk + learning'i birleştirir.

G6 — Confidence calibration:
- Ham confidence (`|score-50|/50`) Platt scaling ile kalibre edilir
  (`packages.learning.calibration_store.predict_calibrated`).
- Kalibrasyon parametresi yoksa identity döner; "insufficient" damgası
  TradeDecision'a yansır.
- **Önemli:** kalibre edilmiş confidence RiskGate'i ASLA bypass etmez.
  KILL_SWITCH → blocked; RISK_REDUCE/NO_POSITION_INCREASE → hold;
  DQS < 55 KILL_SWITCH zaten risk engine'inde uygulanıyor.
- Konsensüs eşiği aşılmadığında yine hold döner (neutral fallback).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_thresholds
from packages.learning.calibration_store import (
    predict_calibrated,
    raw_confidence_from_score,
)
from packages.regime.classifier import RegimeOutput, classify
from packages.risk.engine import RiskDecision, RiskInput
from packages.risk.engine import evaluate as evaluate_risk

Action = Literal["open_long", "open_short", "hold", "blocked"]


@dataclass
class TradeDecision:
    symbol: str
    action: Action
    confidence: float           # calibrated p(win) ∈ [0,1]
    size_multiplier: float      # 0–1.5
    consensus: ConsensusResult
    risk: RiskDecision
    reason: str
    raw_confidence: float = 0.0
    confidence_source: str = "identity"  # identity | fitted | insufficient


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

    raw_conf = raw_confidence_from_score(cons.score)
    cal_conf, conf_source = predict_calibrated(raw_conf)

    # ----- Risk hard gate'leri (calibration BYPASS ETMEZ) -----
    if risk.action == "KILL_SWITCH":
        return TradeDecision(
            symbol=symbol,
            action="blocked",
            confidence=0.0,
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"Risk kapısı: {risk.action}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
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
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
        )

    # ----- Consensus eşikleri -----
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
        # Neutral fallback — yetersiz sinyal.
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason="Consensus eşiği aşılmadı",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
        )

    # Confluence yoksa boyut yarıya iner
    if not cons.confluence_aligned:
        size *= 0.5

    size *= _regime_multiplier(regime.label)

    return TradeDecision(
        symbol=symbol,
        action=action,
        confidence=round(min(0.99, cal_conf), 3),
        size_multiplier=round(size, 3),
        consensus=cons,
        risk=risk,
        reason=f"{cons.direction} signal · dominant={cons.dominant_module}",
        raw_confidence=round(raw_conf, 4),
        confidence_source=conf_source,
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
