"""F4-1 — TF-bazlı Platt kalibrasyonu testleri.

- Store: per_timeframe additive yazılır/okunur; global load() legacy-uyumlu;
  per_timeframe verilmeyen save mevcut TF fit'lerini KORUR.
- Trainer: TF başına fit (örneği yetersiz TF → insufficient, sahte fit yok);
  global fit davranışı birebir eski.
- predict_calibrated_tf: flag KAPALI (default) → global predict birebir
  (bayt-aynı regresyon); AÇIK → TF fit'i varsa "fitted_tf", yoksa global.
- Guardrail: fitted_tf de şişme cap'ine tabi ("fitted_tf_capped").
"""
from __future__ import annotations

import importlib

import pytest

from packages.data.registry.loader import threshold_override
from packages.learning.calibration import apply_platt

_TF_ON = {"calibration": {"tf_platt": True}}


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.learning import calibration_store as cs
    importlib.reload(cs)
    return ps, cs


def _seed(ps, timeframe: str, n_high_win: int, n_low_loss: int) -> None:
    state = ps.load()
    base = len(state.recent_trades)
    for i in range(n_high_win):
        state.recent_trades.append(ps.Trade(
            id=f"{timeframe}-hw{base + i}", symbol="BTCUSD", side="long",
            entry_price=100.0, exit_price=101.0, pnl_usd=80.0,
            opened_at="2026-07-01T00:00:00+00:00", closed_at="2026-07-01T01:00:00+00:00",
            close_reason="TP_HIT", data_verified=True, timeframe=timeframe,
            fingerprint=f"BTCUSD|v2|{timeframe}|NEUTRAL|bullish|S55|C|touche",
            predicted_confidence=0.8, raw_confidence=0.8, confidence_source="identity",
        ))
    for j in range(n_low_loss):
        state.recent_trades.append(ps.Trade(
            id=f"{timeframe}-ll{base + j}", symbol="BTCUSD", side="long",
            entry_price=100.0, exit_price=99.0, pnl_usd=-60.0,
            opened_at="2026-07-01T00:00:00+00:00", closed_at="2026-07-01T01:00:00+00:00",
            close_reason="SL_HIT", data_verified=True, timeframe=timeframe,
            fingerprint=f"BTCUSD|v2|{timeframe}|NEUTRAL|bullish|S55|C|touche",
            predicted_confidence=0.2, raw_confidence=0.2, confidence_source="identity",
        ))
    ps.save(state)


# --------------------------------- store -------------------------------------

def test_store_per_timeframe_roundtrip_and_legacy(fresh_env) -> None:
    _, cs = fresh_env
    # legacy: hiç dosya yok → TF fit'i yok (uydurma parametre yok)
    assert cs.load_tf("15m") is None
    g = cs.CalibrationParams(a=1.2, b=0.1, samples=30, status="fitted")
    tf = cs.CalibrationParams(a=2.0, b=-0.3, samples=12, status="fitted")
    cs.save(g, per_timeframe={"15m": tf})
    assert cs.load().a == 1.2  # global okuma legacy alanlardan (bayt-aynı)
    got = cs.load_tf("15m")
    assert got is not None and got.a == 2.0 and got.status == "fitted"
    # per_timeframe VERİLMEDEN save → mevcut TF fit'leri korunur
    cs.save(cs.CalibrationParams(a=1.3, b=0.0, samples=31, status="fitted"))
    assert cs.load().a == 1.3
    assert cs.load_tf("15m").a == 2.0  # silinmedi


# -------------------------------- trainer ------------------------------------

def test_trainer_fits_per_tf_and_marks_insufficient(fresh_env) -> None:
    ps, cs = fresh_env
    from packages.learning import calibration_trainer as ct
    _seed(ps, "15m", n_high_win=6, n_low_loss=6)   # 12 ≥ MIN_SAMPLES
    _seed(ps, "1d", n_high_win=2, n_low_loss=1)    # 3 < MIN_SAMPLES
    out = ct.train()
    assert out["status"] == "FITTED"               # global: 15 örnek (birebir eski yol)
    assert out["samples"] == 15
    assert out["tf_fitted"] == ["15m"]
    per = out["per_timeframe"]
    assert per["15m"]["status"] == "fitted" and per["15m"]["samples"] == 12
    assert per["1d"]["status"] == "insufficient" and per["1d"]["samples"] == 3
    assert per["1d"]["a"] == 1.0 and per["1d"]["b"] == 0.0  # identity — sahte fit yok
    # store'a da yazıldı
    assert cs.load_tf("15m").status == "fitted"
    assert cs.load_tf("1d").status == "insufficient"


# ------------------------------ predict + flag -------------------------------

def test_predict_tf_flag_off_is_global_byte_same(fresh_env) -> None:
    ps, cs = fresh_env
    from packages.learning import calibration_trainer as ct
    _seed(ps, "15m", n_high_win=6, n_low_loss=6)
    ct.train()
    for raw in (0.1, 0.42, 0.8):
        assert cs.predict_calibrated_tf(raw, "15m") == cs.predict_calibrated(raw)
        assert cs.predict_calibrated_tf(raw, "1d") == cs.predict_calibrated(raw)


def test_predict_tf_flag_on_uses_tf_fit_or_falls_back(fresh_env) -> None:
    ps, cs = fresh_env
    from packages.learning import calibration_trainer as ct
    _seed(ps, "15m", n_high_win=6, n_low_loss=6)
    _seed(ps, "1d", n_high_win=2, n_low_loss=1)
    ct.train()
    tf_params = cs.load_tf("15m")
    with threshold_override(_TF_ON):
        val, source = cs.predict_calibrated_tf(0.8, "15m")
        assert source == "fitted_tf"
        assert val == pytest.approx(
            min(max(apply_platt(0.8, tf_params.a, tf_params.b), 0.0), 1.0), abs=1e-4
        )
        # 1d yetersiz → global fit'e düşer (kaynak global damgası)
        val_1d, source_1d = cs.predict_calibrated_tf(0.8, "1d")
        assert (val_1d, source_1d) == cs.predict_calibrated(0.8)
        # hiç görülmemiş TF → global
        assert cs.predict_calibrated_tf(0.8, "4h") == cs.predict_calibrated(0.8)


def test_guardrail_caps_fitted_tf(fresh_env) -> None:
    _, cs = fresh_env
    # Elle şişiren TF fit'i: apply_platt(0.3, a=1, b=3) ≈ 0.87 → delta 0.05'i aşar
    cs.save(
        cs.CalibrationParams(a=1.0, b=0.0, samples=30, status="fitted"),
        per_timeframe={"15m": cs.CalibrationParams(a=1.0, b=3.0, samples=12, status="fitted")},
    )
    ov = {
        "calibration": {"tf_platt": True},
        "calibration_guardrail": {"enabled": True, "max_inflation_delta": 0.05},
    }
    with threshold_override(ov):
        fitted, source = cs.predict_calibrated_tf(0.3, "15m")
        assert source == "fitted_tf" and fitted > 0.35
        capped, capped_source = cs.apply_inflation_guardrail(0.3, fitted, source)
        assert capped_source == "fitted_tf_capped"
        assert capped == pytest.approx(0.35)
