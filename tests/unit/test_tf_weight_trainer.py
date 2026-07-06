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
        # B5 gerçek raporuyla aynı semantik: kanıt = CALIBRATED + pozitif expectancy
        "edge_proven_timeframes": [
            c["timeframe"] for c in per_tf
            if c["trust"] == "CALIBRATED" and c["expectancy"] > 0
        ],
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
    # Note now reflects which path (entry-outcome fallback or attribution) was used.
    assert "trust-gated" in d["note"]


def test_skip_when_no_prior():
    out = twt.propose({"tf_weights_prior": {}, "per_timeframe": []})
    assert isinstance(out, dict) and out["reason"] == "no_prior_weights"


# ── attributed PnL path: closes the deferred contribution-attribution route ──

def test_proposal_uses_attributed_pnl_when_supplied():
    # 1d calibrated under swing; attributed PnL says 1d earned +100, 4h earned -20.
    rep = _report([_cal("1d", "swing", win_rate=0.6, expectancy=2.0)])
    attributed = {"swing": {"1d": 100.0, "4h": -20.0}}
    p = twt.propose(rep, attributed_pnl=attributed)
    assert isinstance(p, TfWeightProposal)
    assert "contribution attribution" in p.note  # attribution path used
    # the validated 1d gets up-weighted vs its prior under attribution
    assert p.proposed["swing"]["d1"] > _PRIOR["swing"]["d1"]


def test_attributed_negative_share_downweights():
    rep = _report([_cal("1h", "intraday", win_rate=0.6, expectancy=1.0)])
    attributed = {"intraday": {"1h": -100.0, "4h": 20.0}}  # 1h lost
    p = twt.propose(rep, attributed_pnl=attributed)
    assert isinstance(p, TfWeightProposal)
    assert p.proposed["intraday"]["h1"] < _PRIOR["intraday"]["h1"]


def test_falls_back_to_entry_outcome_when_no_attribution():
    rep = _report([_cal("1d", "swing", win_rate=0.80, expectancy=5.0)])
    p = twt.propose(rep, attributed_pnl=None)
    assert isinstance(p, TfWeightProposal)
    assert "entry-outcome" in p.note


# ── live tf_weights resolver (trust-gated) ────────────────────────────────────

def test_resolve_live_weights_returns_none_until_trusted():
    rep_untrusted = _report([_cal("1d", "swing", win_rate=0.9, expectancy=5.0, trust="PRIOR")])
    assert twt.resolve_live_tf_weights(rep_untrusted) is None


def test_resolve_live_weights_returns_canonical_keyed_bucket_when_trusted():
    # Build a trusted report (any calibrated TF → trusted)
    rep_trusted = _report([_cal("1h", "intraday", win_rate=0.7, expectancy=3.0)])
    out = twt.resolve_live_tf_weights(rep_trusted)
    # Trusted → either a canonical-keyed bucket or None (if active manifest empty)
    if out is not None:
        # canonical keys are 15m / 1h / 4h / 1d
        assert all(k in {"15m", "1h", "4h", "1d", "1w"} for k in out)


# ── D4: per-TF trust kapısı (TF_TRUST_PER_BUCKET, default OFF) ────────────────

_MANIFEST = {"tf_weights": {"intraday": {"m15": 0.8, "h1": 1.3, "h4": 1.2, "d1": 0.7}}}


def test_per_bucket_off_is_byte_same(monkeypatch):
    """KAPALI-bekçi: flag yokken kanıt yalnız 1h'de bile olsa BEŞ TF'in öğrenilmiş
    ağırlığı aynen akar (eski gevşek davranış birebir — kural 1)."""
    monkeypatch.setattr(twt, "load_active_weights", lambda: dict(_MANIFEST))
    rep = _report([_cal("1h", "intraday", win_rate=0.7, expectancy=3.0)])
    out = twt.resolve_live_tf_weights(rep)
    assert out == {"15m": 0.8, "1h": 1.3, "4h": 1.2, "1d": 0.7}


def test_per_bucket_on_neutralises_unproven_tfs(monkeypatch):
    """AÇIK: öğrenilmiş ağırlık yalnız kanıtlı TF'e akar; kanıtsızlar nötr 1.0
    (15m, 1d'nin kanıtıyla içeri giremez)."""
    monkeypatch.setattr(twt, "load_active_weights", lambda: dict(_MANIFEST))
    monkeypatch.setenv(twt.FLAG_PER_BUCKET, "1")
    rep = _report([_cal("1h", "intraday", win_rate=0.7, expectancy=3.0)])
    out = twt.resolve_live_tf_weights(rep)
    assert out == {"15m": 1.0, "1h": 1.3, "4h": 1.0, "1d": 1.0}


def test_per_bucket_on_all_proven_unchanged(monkeypatch):
    """AÇIK + tüm TF'ler kanıtlı → sertleştirme hiçbir şeyi değiştirmez."""
    monkeypatch.setattr(twt, "load_active_weights", lambda: dict(_MANIFEST))
    monkeypatch.setenv(twt.FLAG_PER_BUCKET, "1")
    rep = _report([
        _cal("15m", "scalp", win_rate=0.6, expectancy=1.0),
        _cal("1h", "intraday", win_rate=0.7, expectancy=3.0),
        _cal("4h", "intraday", win_rate=0.6, expectancy=2.0),
        _cal("1d", "swing", win_rate=0.6, expectancy=2.0),
    ])
    out = twt.resolve_live_tf_weights(rep)
    assert out == {"15m": 0.8, "1h": 1.3, "4h": 1.2, "1d": 0.7}


def test_per_bucket_on_stale_report_without_field_is_honest(monkeypatch):
    """AÇIK + eski artifact'ta edge_proven_timeframes YOK → hiçbir TF kanıtlı
    sayılmaz, hepsi nötr (sahte kanıt uydurulmaz)."""
    monkeypatch.setattr(twt, "load_active_weights", lambda: dict(_MANIFEST))
    monkeypatch.setenv(twt.FLAG_PER_BUCKET, "1")
    rep = _report([_cal("1h", "intraday", win_rate=0.7, expectancy=3.0)])
    del rep["edge_proven_timeframes"]
    out = twt.resolve_live_tf_weights(rep)
    assert out == {"15m": 1.0, "1h": 1.0, "4h": 1.0, "1d": 1.0}


def test_per_bucket_negative_expectancy_tf_not_proven(monkeypatch):
    """AÇIK: bol örnekli ama para KAYBEDEN TF (CALIBRATED, expectancy<0) kanıtlı
    değildir → nötr kalır (B5 kuralının per-TF devamı)."""
    monkeypatch.setattr(twt, "load_active_weights", lambda: dict(_MANIFEST))
    monkeypatch.setenv(twt.FLAG_PER_BUCKET, "1")
    rep = _report([
        _cal("1h", "intraday", win_rate=0.7, expectancy=3.0),
        _cal("4h", "intraday", win_rate=0.55, expectancy=-1.0),  # kaybeden
    ])
    out = twt.resolve_live_tf_weights(rep)
    assert out is not None and out["1h"] == 1.3 and out["4h"] == 1.0
