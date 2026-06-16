"""Step 8 — tf_weights auto-tune proposal (trust-gated, owner-gated, never applied).

Synthetic calibration reports exercise the trust gate, nudge direction, the
negative-expectancy guard, and bucket-total preservation. The proposal is informational
only — these tests never apply weights.
"""
from __future__ import annotations

from packages.learning import tf_weight_trainer as twt
from packages.learning.tf_weight_trainer import TfWeightProposal

_PRIOR = {
    "swing": {"d1": 0.50, "h4": 0.35, "h1": 0.15, "m15": 0.00},
    "intraday": {"d1": 0.15, "h4": 0.35, "h1": 0.35, "m15": 0.15},
    "scalp": {"d1": 0.00, "h4": 0.15, "h1": 0.35, "m15": 0.50},
}


def _cal(tf, strategy, *, win_rate, expectancy, trust="CALIBRATED", trades=25):
    return {
        "timeframe": tf, "strategy": strategy, "trades": trades, "verified": trades,
        "win_rate": win_rate, "expectancy": expectancy, "trust": trust,
    }


def _report(per_tf):
    return {
        "min_trades_per_tf": 20,
        "tf_weights_prior": {k: dict(v) for k, v in _PRIOR.items()},
        "per_timeframe": per_tf,
        "tf_weights_trusted": any(c["trust"] == "CALIBRATED" for c in per_tf),
        "calibrated_timeframes": [c["timeframe"] for c in per_tf if c["trust"] == "CALIBRATED"],
    }


def test_skip_when_no_calibrated_tf():
    rep = _report([_cal("1d", "swing", win_rate=0.9, expectancy=5.0, trust="PRIOR")])
    out = twt.propose(rep)
    assert isinstance(out, dict) and out["reason"] == "no_calibrated_tf"


def test_nudges_up_high_winrate_calibrated_tf():
    rep = _report([_cal("1d", "swing", win_rate=0.80, expectancy=5.0)])
    p = twt.propose(rep)
    assert isinstance(p, TfWeightProposal)
    # the validated TF gains weight relative to its prior; bucket total is preserved
    assert p.proposed["swing"]["d1"] > _PRIOR["swing"]["d1"]
    assert abs(sum(p.proposed["swing"].values()) - sum(_PRIOR["swing"].values())) < 1e-6
    assert any(d.timeframe == "d1" and d.delta > 0 for d in p.deltas)


def test_never_upweights_negative_expectancy():
    # High win-rate but losing money → factor capped at 0 → no change → skip.
    rep = _report([_cal("1d", "swing", win_rate=0.80, expectancy=-2.0)])
    out = twt.propose(rep)
    assert isinstance(out, dict) and out["reason"] == "no_change"


def test_downweights_low_winrate_tf():
    rep = _report([_cal("1h", "intraday", win_rate=0.30, expectancy=1.0)])
    p = twt.propose(rep)
    assert isinstance(p, TfWeightProposal)
    assert p.proposed["intraday"]["h1"] < _PRIOR["intraday"]["h1"]


def test_bias_only_1w_is_not_tunable():
    # 1w maps to bias_only (no tf_weights bucket) → not tunable → skip.
    rep = _report([_cal("1w", "bias_only", win_rate=0.9, expectancy=5.0)])
    out = twt.propose(rep)
    assert isinstance(out, dict) and out["reason"] == "no_calibrated_tf"


def test_all_buckets_remain_normalised():
    rep = _report([
        _cal("1d", "swing", win_rate=0.75, expectancy=3.0),
        _cal("1h", "intraday", win_rate=0.25, expectancy=0.5),
    ])
    p = twt.propose(rep)
    assert isinstance(p, TfWeightProposal)
    for strat, weights in p.proposed.items():
        assert abs(sum(weights.values()) - sum(_PRIOR[strat].values())) < 1e-6
        assert all(w >= 0.0 for w in weights.values())


def test_proposal_to_dict_shape():
    rep = _report([_cal("1d", "swing", win_rate=0.80, expectancy=5.0)])
    d = twt.proposal_to_dict(twt.propose(rep))
    assert {"prior", "proposed", "deltas", "calibrated_timeframes", "note"} <= set(d)
    assert "deferred" in d["note"]


def test_skip_when_no_prior():
    out = twt.propose({"tf_weights_prior": {}, "per_timeframe": []})
    assert isinstance(out, dict) and out["reason"] == "no_prior_weights"
