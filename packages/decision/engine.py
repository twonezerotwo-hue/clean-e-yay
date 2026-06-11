"""DecisionEngine — consensus + risk + learning'i birleştirir.

G6 — Confidence calibration:
- Ham confidence (`|score-50|/50`) Platt scaling ile kalibre edilir.
- "insufficient" damgası TradeDecision'a yansır.

G3 — Mistake memory gate:
- Consensus eşiği aşıldıktan sonra mistake memory `evaluate(fingerprint)`
  çağrılır. AVOID→hold, BOOST→size_factor×, WARNING→size_factor×.
- NEUTRAL/insufficient → no_adjustment (size_factor=1.0).

G4 — Correlation-aware sizing:
- Mistake gate'ten sonra `cluster_exposure(open_positions, aday)` çağrılır.
  Aynı yönlü |rho| ≥ 0.7 cluster toplamı `max_cluster_pct`'yi aştıysa →
  hold; yarısını aştıysa size×0.5. **Sadece küçültür, asla artırmaz.**
  Veri yetersizse neutral fallback (adjustment yok).

**Hard kural:** mistake memory, calibration ve correlation sizing
**RiskGate'i bypass ETMEZ**. KILL_SWITCH→blocked;
RISK_REDUCE/NO_POSITION_INCREASE→hold.
DQS < 55 zaten risk engine'inde KILL_SWITCH üretir → BLOCKED state'te trade
yok (calibration BOOST veya mistake BOOST yüksek olsa bile).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from packages.consensus.engine import ConsensusResult
from packages.consensus.engine import build as build_consensus
from packages.data.ingestion.pipeline import MarketSnapshot
from packages.data.registry.loader import load_thresholds
from packages.learning import mistake_memory
from packages.learning.calibration_store import (
    predict_calibrated,
    raw_confidence_from_score,
)
from packages.learning.fingerprint import make as make_fingerprint
from packages.learning.mistake_memory import MistakeVerdict
from packages.regime.classifier import RegimeOutput, classify
from packages.risk import correlation
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
    confidence_source: str = "identity"
    fingerprint: str | None = None
    mistake_verdict: dict = field(default_factory=dict)
    cluster_report: dict = field(default_factory=dict)


def _regime_multiplier(label: str) -> float:
    return {"OFFENSIVE": 1.0, "NEUTRAL": 0.8, "DEFENSIVE": 0.5, "CRISIS": 0.35}.get(label, 0.5)


def _verdict_to_dict(v: MistakeVerdict) -> dict:
    return {
        "action": v.action,
        "reason": v.reason,
        "size_factor": v.size_factor,
        "evidence": list(v.evidence),
        "fingerprint": v.fingerprint,
        "record": asdict(v.record) if v.record else None,
    }


def decide_for_symbol(
    symbol: str,
    snap: MarketSnapshot,
    regime: RegimeOutput,
    risk: RiskDecision,
    mistakes: list | None = None,
    open_positions: list | None = None,
    equity_usd: float = 0.0,
    corr_entries: list | None = None,
) -> TradeDecision:
    th = load_thresholds()["consensus"]
    cons = build_consensus(symbol, snap, regime)

    raw_conf = raw_confidence_from_score(cons.score)
    cal_conf, conf_source = predict_calibrated(raw_conf)

    # Fingerprint hesabı (mistake memory için her zaman üret — debugging).
    fp = make_fingerprint(
        symbol=symbol,
        regime=regime.label,
        direction=cons.direction,
        score=cons.score,
        confluence=cons.confluence_aligned,
        dominant_module=cons.dominant_module or "?",
    )

    # ----- Risk hard gate'leri (mistake memory & calibration BYPASS ETMEZ) -----
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
            fingerprint=fp,
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
            fingerprint=fp,
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
            fingerprint=fp,
        )

    # Confluence yoksa boyut yarıya iner
    if not cons.confluence_aligned:
        size *= 0.5
    size *= _regime_multiplier(regime.label)

    # ----- G3: Mistake memory gate (RiskGate'i ASLA bypass etmez) -----
    verdict = mistake_memory.evaluate(fp, mistakes)
    if verdict.action == "AVOID":
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=f"mistake_memory: {verdict.reason}",
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
        )

    size *= verdict.size_factor
    size = max(0.0, min(1.5, size))

    # ----- G4: Correlation cluster cap (sadece küçültür, RiskGate'i bypass etmez) -----
    cluster = correlation.cluster_exposure(
        open_positions or [],
        symbol,
        "long" if action == "open_long" else "short",
        equity_usd,
        entries=corr_entries,
    )
    cluster_dict = asdict(cluster)
    if cluster.size_factor <= 0.0:
        return TradeDecision(
            symbol=symbol,
            action="hold",
            confidence=round(cal_conf, 3),
            size_multiplier=0.0,
            consensus=cons,
            risk=risk,
            reason=(
                f"correlation_cluster: aynı yönlü exposure {cluster.cluster_pct:.0%}"
                f" ≥ cap {cluster.max_cluster_pct:.0%}"
            ),
            raw_confidence=round(raw_conf, 4),
            confidence_source=conf_source,
            fingerprint=fp,
            mistake_verdict=_verdict_to_dict(verdict),
            cluster_report=cluster_dict,
        )
    size *= min(1.0, cluster.size_factor)
    size = max(0.0, min(1.5, size))

    return TradeDecision(
        symbol=symbol,
        action=action,
        confidence=round(min(0.99, cal_conf), 3),
        size_multiplier=round(size, 3),
        consensus=cons,
        risk=risk,
        reason=(
            f"{cons.direction} signal · dominant={cons.dominant_module}"
            + (f" · mistake:{verdict.action.lower()}" if verdict.action != "NEUTRAL" else "")
            + (f" · correlation:{cluster.status.lower()}" if cluster.status != "OK" else "")
        ),
        raw_confidence=round(raw_conf, 4),
        confidence_source=conf_source,
        fingerprint=fp,
        mistake_verdict=_verdict_to_dict(verdict),
        cluster_report=cluster_dict,
    )


def decide_all(
    symbols: list[str],
    snap: MarketSnapshot,
    paper_state_input: RiskInput,
    open_positions: list | None = None,
) -> tuple[RegimeOutput, RiskDecision, list[TradeDecision]]:
    regime = classify(snap)
    risk = evaluate_risk(paper_state_input)
    # Tek pass mistake özeti — tüm semboller için aynı snapshot.
    mems = mistake_memory.summary()
    positions = open_positions or []
    # Korelasyon matrisi tek pass (aday + açık pozisyon sembolleri).
    corr_entries = correlation.matrix(
        sorted({*symbols, *(p.symbol for p in positions)})
    )
    decisions = [
        decide_for_symbol(
            s,
            snap,
            regime,
            risk,
            mistakes=mems,
            open_positions=positions,
            equity_usd=paper_state_input.equity_usd,
            corr_entries=corr_entries,
        )
        for s in symbols
    ]
    return regime, risk, decisions
