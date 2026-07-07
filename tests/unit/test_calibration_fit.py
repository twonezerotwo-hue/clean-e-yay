"""Faz-A (Kalibrasyon) — per-TF Platt fit güven yüzeyi testleri.

- fit_confidence_report(): calibration_store fit durumu (fitted/insufficient/
  identity) + outcome güveni yan yana; fitted TF'ler listelenir; guard notu.
- calibration_store'da fit yoksa identity; boş → NO_DATA değil (store TF'leri).
"""
from __future__ import annotations

import pytest

from packages.learning import calibration_store
from packages.learning import tf_calibration as tc
from packages.learning.calibration_store import CalibrationParams


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "calib.json"))
    return tmp_path


def _seed(**tf_specs):
    """tf → (status, samples) → store'a per_timeframe fit yaz."""
    per_tf = {
        tf: CalibrationParams(a=1.2, b=-0.1, samples=n, status=st, fitted_at="2026-07-07")
        for tf, (st, n) in tf_specs.items()
    }
    calibration_store.save(CalibrationParams(status="fitted", samples=100), per_timeframe=per_tf)


def test_fitted_tf_surfaces_as_fitted(store_path):
    _seed(**{"1d": ("fitted", 30), "4h": ("insufficient", 5)})
    r = tc.fit_confidence_report(outcomes=[])
    by_tf = {row["timeframe"]: row for row in r["per_timeframe_fit"]}
    assert by_tf["1d"]["fit_status"] == "fitted" and by_tf["1d"]["fit_samples"] == 30
    assert by_tf["4h"]["fit_status"] == "insufficient"
    assert "1d" in r["fitted_timeframes"] and "4h" not in r["fitted_timeframes"]
    assert r["any_fitted"] is True
    assert r["shadow_only"] is True


def test_no_fit_means_no_fitted_timeframes(store_path):
    r = tc.fit_confidence_report(outcomes=[])
    assert r["fitted_timeframes"] == []
    assert r["any_fitted"] is False


def test_report_shape(store_path):
    _seed(**{"1d": ("fitted", 22)})
    r = tc.fit_confidence_report(outcomes=[])
    for k in ("status", "tf_platt_enabled", "per_timeframe_fit",
              "fitted_timeframes", "any_fitted", "min_trades_per_tf"):
        assert k in r
    row = r["per_timeframe_fit"][0]
    for k in ("timeframe", "fit_status", "fit_samples", "outcome_trust", "outcome_n"):
        assert k in row
