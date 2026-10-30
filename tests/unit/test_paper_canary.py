from __future__ import annotations

from datetime import UTC, datetime

from packages.learning import paper_canary


def _idea(*, symbol="TEST", source=None, news=None, verdict="WOULD_OPEN_LONG", tf="15m"):
    return {
        "symbol": symbol,
        "name": "Test asset",
        "score": 70,
        "technical": {
            "verdict": verdict,
            "entry_timeframe": tf,
            "confidence": 0.7,
            "expected_value": 0.2,
            "entry": 100.0,
            "ta": {"bias": "BULLISH" if verdict.endswith("LONG") else "BEARISH", "confirmations": ["ema_stack"]},
        },
        "source": source or {"provider": "test", "provider_id": symbol, "mapped_for_paper": True,
                              "discovery_price": 100.0, "current_price": 100.0,
                              "current_price_verified": True},
        "news": news or {"evidence_status": "CONFIRMED", "independent_source_families": 2,
                          "source_families": ["direct:a", "direct:b"], "direction": "up",
                          "conflict": False, "n_stories": 2},
    }


def _learning():
    return {
        "performance": {"by_timeframe": {"15m": {"trades": 24, "avg_r": 0.1},
                                           "1h": {"trades": 22, "avg_r": -0.1}}},
        "signal_quality": {"overall": {"fundamental": {"verdict": "FLAT"}}, "per_regime": {}},
    }


def _race(**overrides):
    out = {"race_status": "V4_AHEAD", "resolved": 50, "beats_backup": True, "beats_baseline": True,
           "checks": {"ci_disjoint": {"pass": True}}}
    out.update(overrides)
    return out


def test_paper_canary_requires_all_evidence_before_owner_pending():
    report = paper_canary.build_report(
        datetime(2026, 1, 1, tzinfo=UTC),
        learning=_learning(),
        entry_report={"buckets": []},
        exit_report={"per_tf_best": {"15m": {"avg_r": 0.2}}},
        race=_race(),
        ideas=[_idea()],
        forecasts={},
        regime_report={},
    )
    candidate = report["candidates"][0]
    assert candidate["status"] == "PAPER_CANARY_PENDING_OWNER"
    assert report["automatic_activation"] is False
    assert report["no_execution"] is True


def test_paper_canary_blocks_price_news_and_holdout_gaps():
    idea = _idea(
        source={"provider": None, "mapped_for_paper": False, "discovery_price": None},
        news={"evidence_status": "SINGLE_SOURCE", "independent_source_families": 1,
              "direction": "up", "conflict": False},
    )
    report = paper_canary.build_report(
        learning=_learning(), entry_report={"buckets": []}, exit_report={}, race=_race(beats_baseline=False),
        ideas=[idea], forecasts={}, regime_report={},
    )
    candidate = report["candidates"][0]
    assert candidate["status"] == "WAITING_EVIDENCE"
    assert any("asset_price_source:" in row for row in candidate["blocked_by"])
    assert any("news_consensus:" in row for row in candidate["blocked_by"])
    assert any("holdout:" in row for row in candidate["blocked_by"])


def test_one_hour_negative_analysis_is_explicit():
    report = paper_canary.build_report(
        learning=_learning(), entry_report={"buckets": [{"module": "x", "timeframe": "1h",
                                                        "verdicts": [{"code": "ENTER_EARLY", "detail": "delay"}]}]},
        exit_report={}, race={}, ideas=[], forecasts={}, regime_report={},
    )
    one_hour = report["one_hour_analysis"]
    assert one_hour["status"] == "REVIEW_REQUIRED"
    assert one_hour["avg_r"] == -0.1
    assert one_hour["diagnoses"][0]["code"] == "ENTER_EARLY"


def test_timeframe_canary_keeps_1h_and_4h_shadow_only():
    report = paper_canary.build_report(
        learning={"performance": {"by_timeframe": {"1h": {"trades": 20, "avg_r": 0.1},
                                                       "4h": {"trades": 2, "avg_r": 0.2}}}},
        entry_report={},
        exit_report={"per_tf_best": {"1h": {"avg_r": 0.05}}},
        race={},
        ideas=[],
        forecasts={},
        regime_report={},
    )
    assert set(report["timeframe_canary"]) == {"1h", "4h"}
    assert report["timeframe_canary"]["1h"]["status"] == "READY"
    assert report["timeframe_canary"]["4h"]["status"] == "REVIEW_REQUIRED"
    assert report["timing_canary"]["exit_backtest"]["activation"] == "SHADOW_ONLY"


def test_regime_inverse_evidence_keeps_weights_observe_only():
    report = paper_canary.build_report(
        learning={"performance": {}, "signal_quality": {"overall": {"quantum": {"verdict": "INVERSE"}}}},
        entry_report={}, exit_report={}, race={}, ideas=[], forecasts={}, regime_report={"enabled": True},
    )
    regime = report["regime_weight_test"]
    assert regime["status"] == "HOLD"
    assert regime["weight_changes"] == []
