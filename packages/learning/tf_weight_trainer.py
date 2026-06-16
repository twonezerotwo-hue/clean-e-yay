"""Step 8 — tf_weights auto-tune (trust-gated proposal; owner-gated, never applied).

Honest scope (no faking): full per-TF signal-CONTRIBUTION attribution (how much each
timeframe's signal pushed each decision) needs richer per-TF decision logging and stays
deferred. What is honestly derivable today is the per-TF entry OUTCOME — hit-rate and
expectancy of trades entered on each timeframe — which `tf_calibration` already computes
from VERIFIED outcomes.

This trainer turns that into a conservative per-strategy `tf_weights` PROPOSAL:

  * Trust gate — only timeframes the calibration has validated (trust == CALIBRATED,
    i.e. ≥ MIN_TRADES verified outcomes) may be nudged. Until then the PRIOR stands.
  * A timeframe's weight is nudged within ±`max_drift` from its win-rate edge; a TF with
    non-positive expectancy is never up-weighted (don't reward a losing timeframe).
  * Each strategy bucket is renormalised to its prior total, so the proposal only
    *rebalances* validated weight — it never invents new total conviction.
  * It is NEVER auto-applied. Owner approval moves live weights (mirrors
    `auto_weight_trainer`); this only proposes.

Only the entry-TF's own weight in its strategy bucket is tuned (1d→swing, 1h/4h→
intraday, 15m→scalp); 1w yields bias only and is never an entry. Cross-TF weights stay
at PRIOR until contribution attribution lands.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from packages.learning import tf_calibration

MIN_TRADES = tf_calibration.MIN_TRADES_PER_TF  # validate before tuning (== calibration gate)
MAX_DRIFT = 0.10  # max relative change to a validated TF's weight per proposal

# canonical timeframe → config tf_weights key (per-strategy buckets use these keys).
_TF_KEY: dict[str, str] = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}


@dataclass
class TfWeightDelta:
    strategy: str
    timeframe: str  # config key (m15/h1/h4/d1)
    old: float
    new: float
    delta: float


@dataclass
class TfWeightProposal:
    generated_at: str
    prior: dict
    proposed: dict
    deltas: list[TfWeightDelta]
    calibrated_timeframes: list[str] = field(default_factory=list)
    note: str = (
        "entry-outcome based, trust-gated; full per-TF contribution attribution deferred"
    )


def _nudge_factor(win_rate: float, expectancy: float) -> float:
    """Edge in [-1, 1] from win-rate; never positive when expectancy ≤ 0."""
    factor = max(-1.0, min(1.0, (win_rate - 0.5) * 2.0))
    if expectancy <= 0.0:
        factor = min(factor, 0.0)  # never up-weight a losing timeframe
    return factor


def _renormalise(bucket: dict, prior_total: float) -> dict:
    total = sum(float(v) for v in bucket.values())
    if total <= 0.0:
        return bucket
    scale = prior_total / total
    return {k: round(float(v) * scale, 4) for k, v in bucket.items()}


def propose(
    report: dict | None = None,
    *,
    prior: dict | None = None,
    max_drift: float = MAX_DRIFT,
    min_trades: int = MIN_TRADES,
) -> TfWeightProposal | dict:
    """Build a trust-gated tf_weights proposal, or a skip dict when there is no
    validated timeframe yet (the normal state until verified outcomes accumulate)."""
    report = report if report is not None else tf_calibration.calibration_report(min_trades=min_trades)
    prior = prior if prior is not None else dict(report.get("tf_weights_prior", {}) or {})
    if not prior:
        return {"status": "skipped", "reason": "no_prior_weights"}

    per_tf = report.get("per_timeframe", []) or []
    calibrated = [c for c in per_tf if c.get("trust") == "CALIBRATED"]
    # An entry-TF is tunable only if it is calibrated AND lives in a tf_weights bucket.
    tunable = [
        c for c in calibrated
        if c.get("strategy") in prior and _TF_KEY.get(c.get("timeframe", "")) in (prior.get(c.get("strategy"), {}))
    ]
    if not tunable:
        return {"status": "skipped", "reason": "no_calibrated_tf"}

    proposed = {strat: dict(weights) for strat, weights in prior.items()}
    deltas: list[TfWeightDelta] = []
    touched_strategies: set[str] = set()
    for c in tunable:
        strat = c["strategy"]
        key = _TF_KEY[c["timeframe"]]
        old = float(prior[strat][key])
        factor = _nudge_factor(float(c.get("win_rate", 0.0)), float(c.get("expectancy", 0.0)))
        new = round(old * (1.0 + max_drift * factor), 4)
        proposed[strat][key] = new
        touched_strategies.add(strat)

    # Renormalise each touched bucket back to its prior total (rebalance, not inflate).
    for strat in touched_strategies:
        prior_total = sum(float(v) for v in prior[strat].values())
        proposed[strat] = _renormalise(proposed[strat], prior_total)
        for key in prior[strat]:
            old = round(float(prior[strat][key]), 4)
            new = round(float(proposed[strat][key]), 4)
            if new != old:
                deltas.append(TfWeightDelta(strategy=strat, timeframe=key, old=old, new=new, delta=round(new - old, 4)))

    if not deltas:
        return {"status": "skipped", "reason": "no_change"}

    return TfWeightProposal(
        generated_at=datetime.now(UTC).isoformat(),
        prior=prior,
        proposed=proposed,
        deltas=deltas,
        calibrated_timeframes=list(report.get("calibrated_timeframes", []) or []),
    )


def proposal_to_dict(p: TfWeightProposal) -> dict:
    return asdict(p)
