"""L2 (step 8) — per-timeframe calibration of the new technical pipeline.

Connects verified paper outcomes → per-TF hit-rate / expectancy so the consensus
`tf_weights` can be TRUSTED only AFTER calibration validates them (spec §8:
"tf_weights PRIOR olarak başlar; kalibrasyon onları doğrulayana kadar güvenme").

No new data source — derives from existing `CanonicalOutcome`s. DATA_POLICY:
verified-only. PAPER_SAFE / NO_EXECUTION: read-only; proposes nothing live and
never mutates weights.

Scope note (no faking): the full attribution-based tf_weight AUTO-TUNE (per-TF
signal contribution vs. outcome) needs richer per-TF decision logging and is
intentionally deferred. This lands the honest calibration foundation + the trust
gate that keeps tf_weights at PRIOR until there is enough verified evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from packages.data.registry.loader import load_active_weights
from packages.learning import outcomes as outcomes_mod
from packages.learning.outcomes import CanonicalOutcome

# Verified-outcome count a TF needs before its weight may be trusted/tuned.
MIN_TRADES_PER_TF = 20

# Entry-TF → strategy column (spec §3). 1w yields bias only (no entry).
_TF_STRATEGY: dict[str, str] = {
    "15m": "scalp",
    "1h": "intraday",
    "4h": "intraday",
    "1d": "swing",
    "1w": "bias_only",
}


@dataclass
class TimeframeCalibration:
    timeframe: str
    strategy: str
    trades: int          # verified outcomes (== verified; DATA_POLICY)
    verified: int
    win_rate: float
    expectancy: float    # mean PnL per verified outcome
    trust: str           # "PRIOR" until calibrated, then "CALIBRATED"


def per_timeframe_calibration(
    outcomes: list[CanonicalOutcome], *, min_trades: int = MIN_TRADES_PER_TF
) -> list[TimeframeCalibration]:
    """Per-TF hit-rate + expectancy from VERIFIED outcomes (DATA_POLICY).

    A timeframe is `CALIBRATED` only once it has ≥ ``min_trades`` verified
    outcomes; otherwise it stays `PRIOR` (its weight must not be trusted yet).
    """
    by_tf: dict[str, list[CanonicalOutcome]] = {}
    for o in outcomes:
        if not o.data_verified:
            continue  # unverified / mock / DATA_UNAVAILABLE never calibrates
        by_tf.setdefault(o.timeframe, []).append(o)

    cals: list[TimeframeCalibration] = []
    for tf, items in sorted(by_tf.items()):
        n = len(items)
        wins = sum(1 for o in items if o.pnl > 0)
        expectancy = round(sum(o.pnl for o in items) / n, 2) if n else 0.0
        cals.append(
            TimeframeCalibration(
                timeframe=tf,
                strategy=_TF_STRATEGY.get(tf, "unknown"),
                trades=n,
                verified=n,
                win_rate=round(wins / n, 3) if n else 0.0,
                expectancy=expectancy,
                trust="CALIBRATED" if n >= min_trades else "PRIOR",
            )
        )
    return cals


def load_tf_weight_prior() -> dict:
    """PRIOR per-strategy tf_weights from the active weights manifest (may be empty)."""
    return dict(load_active_weights().get("tf_weights", {}) or {})


def calibration_report(
    outcomes: list[CanonicalOutcome] | None = None,
    *,
    state=None,
    min_trades: int = MIN_TRADES_PER_TF,
) -> dict:
    """Per-TF calibration + the tf_weights trust verdict (read-only ViewModel).

    `tf_weights_trusted` is True only when at least one timeframe is CALIBRATED —
    until then the PRIOR weights stand (spec §8 discipline).
    """
    outs = outcomes if outcomes is not None else outcomes_mod.outcomes_from_state(state)
    cals = per_timeframe_calibration(outs, min_trades=min_trades)
    calibrated = [c.timeframe for c in cals if c.trust == "CALIBRATED"]
    return {
        "min_trades_per_tf": min_trades,
        "tf_weights_prior": load_tf_weight_prior(),
        "per_timeframe": [asdict(c) for c in cals],
        "tf_weights_trusted": bool(calibrated),
        "calibrated_timeframes": calibrated,
    }
