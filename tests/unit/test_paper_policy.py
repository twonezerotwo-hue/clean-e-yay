from __future__ import annotations

from packages.decision import paper_policy


def test_paper_auto_open_requires_explicit_paper_environment(monkeypatch):
    monkeypatch.setattr(
        paper_policy,
        "load_thresholds",
        lambda: {"paper_trading": {"paper_auto_open": {"enabled": True}}},
    )
    monkeypatch.delenv("PAPER_ONLY", raising=False)
    monkeypatch.delenv("NO_EXECUTION", raising=False)
    assert paper_policy.enabled() is False

    monkeypatch.setenv("PAPER_ONLY", "true")
    monkeypatch.setenv("NO_EXECUTION", "true")
    assert paper_policy.enabled() is True


def test_paper_auto_open_is_bounded():
    cfg = paper_policy.PaperAutoOpenConfig(
        enabled=True,
        min_confidence=0.20,
        max_negative_ev=-0.40,
        max_size_multiplier=0.35,
    )
    assert paper_policy.allows_confidence(0.20, cfg)
    assert not paper_policy.allows_confidence(0.19, cfg)
    assert paper_policy.allows_expected_value(-0.40, cfg)
    assert not paper_policy.allows_expected_value(-0.41, cfg)
    assert paper_policy.cap_size(1.0, cfg) == 0.35


def test_decision_can_collect_soft_gate_evidence_only_in_paper_mode(monkeypatch):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine
    from packages.regime.classifier import classify
    from packages.risk.engine import RiskDecision

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD",
        score=66.0,
        direction="bullish",
        confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=66.0, weight=1.0, contribution=66.0)],
    )
    monkeypatch.setattr(engine, "build_consensus", lambda *a, **kw: fake)
    monkeypatch.setattr(engine, "predict_calibrated_tf", lambda *a, **kw: (0.35, "test"))
    monkeypatch.setattr(engine, "_ev_gate_cfg", lambda: {"enabled": True, "min_ev": 0.0, "cost_r": 0.25})
    monkeypatch.setattr(
        paper_policy,
        "load_config",
        lambda: paper_policy.PaperAutoOpenConfig(
            enabled=True, min_confidence=0.20, max_negative_ev=-0.40, max_size_multiplier=0.35
        ),
    )
    risk = RiskDecision(action="HOLD", reason="ok", evidence=[])

    normal = engine.decide_for_symbol(
        "BTCUSD", snap, regime, risk, open_positions=[], equity_usd=100_000, timeframe="1d"
    )
    exploratory = engine.decide_for_symbol(
        "BTCUSD", snap, regime, risk, open_positions=[], equity_usd=100_000,
        timeframe="1d", paper_exploration=True,
    )
    assert normal.action == "hold"
    assert "ev_gate" in normal.blocked_by
    assert exploratory.action == "open_long"
    assert exploratory.size_multiplier <= 0.35
    assert "paper_exploration:ev_gate" in exploratory.blocked_by
