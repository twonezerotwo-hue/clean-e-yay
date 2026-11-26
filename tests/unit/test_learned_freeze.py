"""L1 (26 Kasım 2026, owner "önce dondur"): öğrenilen tablolar canlıda kendiliğinden
değişmez; öğrenme işçisi öneriyi yanına yazar ve farkı koşu kaydına düşer."""
from __future__ import annotations

import json


def _write(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_learned_drift_reports_proposal_vs_live(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("EMPIRICAL_PWIN_PATH", str(tmp_path / "empirical_pwin.json"))
    monkeypatch.setenv("REGIME_RISK_BRAKE_PATH", str(tmp_path / "regime_risk_brake.json"))
    from apps.learning_worker import main as lw
    from packages.learning import calibration_store as cs
    from packages.learning import empirical_pwin as ep
    from packages.learning import regime_risk_brake as rrb

    assert cs._proposal_path().name == "platt_proposal.json"
    _write(cs._store_path(), {"per_timeframe": {"1h": {"a": 0.3, "b": 0.6}}})
    _write(cs._proposal_path(), {"per_timeframe": {"1h": {"a": 0.25, "b": 0.7}}})
    _write(ep._path(), {"cells": {"1h|NEUTRAL": {"n": 30, "p_win": 0.5}, "4h|CRISIS": {"n": 25, "p_win": 0.4}}})
    _write(ep._proposal_path(), {"min_samples": 20,
                                 "cells": {"1h|NEUTRAL": {"n": 31, "p_win": 0.52},
                                           "4h|CRISIS": {"n": 26, "p_win": 0.3}}})
    _write(rrb._path(), {"braked_regimes": ["CRISIS"]})
    _write(rrb._proposal_path(), {"braked_regimes": ["CRISIS", "NEUTRAL"]})

    drift = lw._learned_drift()
    assert drift["calibration"]["1h"] == [0.3, 0.6, 0.25, 0.7]
    assert drift["empirical_pwin"]["cells_changed"] == ["4h|CRISIS"]  # |Δp| ≥ 0.05
    assert drift["regime_brake"] == {"live": ["CRISIS"], "proposal": ["CRISIS", "NEUTRAL"]}


def test_no_proposal_no_drift(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("EMPIRICAL_PWIN_PATH", str(tmp_path / "empirical_pwin.json"))
    monkeypatch.setenv("REGIME_RISK_BRAKE_PATH", str(tmp_path / "regime_risk_brake.json"))
    from apps.learning_worker import main as lw

    assert lw._learned_drift() == {}
