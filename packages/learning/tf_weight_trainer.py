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

from packages.data.registry.loader import load_active_weights
from packages.learning import tf_calibration

MIN_TRADES = tf_calibration.MIN_TRADES_PER_TF  # validate before tuning (== calibration gate)
MAX_DRIFT = 0.10  # max relative change to a validated TF's weight per proposal

# canonical timeframe → config tf_weights key (per-strategy buckets use these keys).
_TF_KEY: dict[str, str] = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "d1", "1w": "w1"}

# Default live-application strategy bucket. Symbol-specific resolution is a follow-up;
# applying a single trusted bucket is the honest first step (no fake per-symbol pick).
DEFAULT_LIVE_STRATEGY = "intraday"


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


def _attributed_factor(attributed_pnl: float, attributed_total: float) -> float:
    """Edge in [-1, 1] from attributed PnL share — a TF is up-weighted only when its
    share of realized PnL is materially positive. Symmetric for losses."""
    if attributed_total <= 0.0:
        return 0.0
    share = attributed_pnl / attributed_total  # in [-1, 1] when total > 0
    return max(-1.0, min(1.0, share))


def resolve_live_tf_weights(
    report: dict | None = None,
    *,
    strategy: str = DEFAULT_LIVE_STRATEGY,
) -> dict[str, float] | None:
    """Return the active per-TF weight bucket WHEN the trust gate is open, else None.

    Honest gating: until per-TF calibration validates the weights, the consensus
    stays strategy-agnostic (None → equal weighting). Weights only flow once owner-
    approved entries are in the active manifest AND calibration trusts them.
    """
    report = report if report is not None else tf_calibration.calibration_report()
    if not report.get("tf_weights_trusted", False):
        return None
    active = load_active_weights().get("tf_weights", {}) or {}
    bucket = active.get(strategy)
    if not bucket:
        return None
    # Canonical-keyed dict (15m..1w) — what consensus + contribution expect.
    canonical = {"m15": "15m", "h1": "1h", "h4": "4h", "d1": "1d", "w1": "1w"}
    return {canonical[k]: float(v) for k, v in bucket.items() if k in canonical}


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
    attributed_pnl: dict[str, dict[str, float]] | None = None,
) -> TfWeightProposal | dict:
    """Build a trust-gated tf_weights proposal, or a skip dict when there is no
    validated timeframe yet (the normal state until verified outcomes accumulate).

    When `attributed_pnl` is supplied (per-strategy/per-TF realized PnL share from
    the contribution snapshots — see `tf_contribution`), the nudge follows attributed
    PnL share instead of raw entry-outcome win rate. Trust gate still applies: only
    timeframes the calibration validated (CALIBRATED) may move."""
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

    # When attributed PnL is supplied, use it as the nudge driver (proper attribution)
    # for any strategy that has positive total absolute PnL; otherwise fall back to
    # entry-outcome per row (the honest default until contribution data accrues).
    abs_totals: dict[str, float] = {}
    if attributed_pnl:
        for strat, by_tf in attributed_pnl.items():
            abs_totals[strat] = sum(abs(float(v)) for v in by_tf.values())

    proposed = {strat: dict(weights) for strat, weights in prior.items()}
    deltas: list[TfWeightDelta] = []
    touched_strategies: set[str] = set()
    attribution_used = False
    for c in tunable:
        strat = c["strategy"]
        tf_canonical = c["timeframe"]
        key = _TF_KEY[tf_canonical]
        old = float(prior[strat][key])
        if attributed_pnl and abs_totals.get(strat, 0.0) > 0.0:
            ap = float((attributed_pnl.get(strat) or {}).get(tf_canonical, 0.0))
            factor = _attributed_factor(ap, abs_totals[strat])
            attribution_used = True
        else:
            factor = _nudge_factor(
                float(c.get("win_rate", 0.0)), float(c.get("expectancy", 0.0))
            )
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

    note = (
        "per-TF signal-contribution attribution from closed trades, trust-gated"
        if attribution_used
        else "entry-outcome based, trust-gated; contribution attribution falls back when no data"
    )
    return TfWeightProposal(
        generated_at=datetime.now(UTC).isoformat(),
        prior=prior,
        proposed=proposed,
        deltas=deltas,
        calibrated_timeframes=list(report.get("calibrated_timeframes", []) or []),
        note=note,
    )


def proposal_to_dict(p: TfWeightProposal) -> dict:
    return asdict(p)


def _gather_attributed_pnl() -> dict[str, dict[str, float]]:
    """Best-effort: read recent closed trades from paper state and shadow contribution
    snapshots, then attribute realized PnL per (strategy, TF). Returns {} on any
    failure (defensive — trainer falls back to entry-outcome)."""
    try:
        from packages.decision import shadow
        from packages.learning import outcomes as outcomes_mod
        from packages.learning import tf_contribution

        outs = outcomes_mod.outcomes_from_state()
        closed = [
            {
                "snapshot_id": o.snapshot_id,
                "symbol": o.symbol,
                "pnl": float(o.pnl),
                "strategy": tf_calibration._TF_STRATEGY.get(o.timeframe, "unknown"),
            }
            for o in outs
            if getattr(o, "data_verified", False) and o.snapshot_id
        ]
        if not closed:
            return {}
        snaps = shadow.read_recent(limit=500)
        return tf_contribution.attributed_pnl_per_tf(closed, snaps)
    except Exception:
        return {}


def report_viewmodel(report: dict | None = None) -> dict:
    """Flat, render-ready ViewModel: per-TF calibration + the trust-gated proposal.

    Frontend does no math — the per-TF rows and proposed deltas are shaped here. The
    proposal status is `proposed` or the skip reason (e.g. `no_calibrated_tf`). When
    contribution snapshots exist for closed trades, the proposal switches to attributed
    PnL (proper attribution) automatically; otherwise it falls back to entry-outcome."""
    report = report if report is not None else tf_calibration.calibration_report()
    attributed = _gather_attributed_pnl()
    proposal = propose(report, attributed_pnl=attributed or None)
    if isinstance(proposal, TfWeightProposal):
        status = "proposed"
        deltas = [asdict(d) for d in proposal.deltas]
        note = proposal.note
    else:
        status = str(proposal.get("reason", "skipped"))
        deltas = []
        note = (
            "entry-outcome based, trust-gated; contribution attribution falls back when no data"
        )
    return {
        "tf_weights_trusted": bool(report.get("tf_weights_trusted", False)),
        "min_trades_per_tf": report.get("min_trades_per_tf"),
        "calibrated_timeframes": list(report.get("calibrated_timeframes", []) or []),
        "per_timeframe": [
            {
                "timeframe": c.get("timeframe"),
                "strategy": c.get("strategy"),
                "trades": c.get("trades"),
                "win_rate": c.get("win_rate"),
                "expectancy": c.get("expectancy"),
                "trust": c.get("trust"),
            }
            for c in (report.get("per_timeframe") or [])
        ],
        "proposal_status": status,
        "deltas": deltas,
        "attribution_active": bool(attributed),
        "note": note,
    }
