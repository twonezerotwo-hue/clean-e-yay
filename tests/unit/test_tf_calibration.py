"""Step 8 — per-timeframe calibration + tf_weights trust gate.

Verified-only (DATA_POLICY) per-TF hit-rate / expectancy; tf_weights stay PRIOR
until a TF has enough verified outcomes to be CALIBRATED. Read-only / paper-safe.
"""
from __future__ import annotations

from packages.learning import tf_calibration as tc
from packages.learning.outcomes import CanonicalOutcome


def _oc(tf: str, pnl: float, *, verified: bool = True) -> CanonicalOutcome:
    return CanonicalOutcome(
        trade_id="t",
        symbol="BTCUSD",
        timeframe=tf,
        opened_at=None,
        closed_at=None,
        duration_seconds=None,
        direction="long",
        open_price=None,
        close_price=None,
        pnl=pnl,
        pnl_pct=None,
        open_reason=None,
        close_reason=None,
        fingerprint=None,
        regime="NEUTRAL",
        dominant_module="technical",
        candidate_action="open_long",
        final_action="open_long",
        data_verified=verified,
    )


# ── DATA_POLICY: unverified outcomes never calibrate ──────────────────────────

def test_only_verified_outcomes_calibrate():
    outs = [_oc("1h", 10.0, verified=True), _oc("1h", -5.0, verified=False)]
    cals = tc.per_timeframe_calibration(outs, min_trades=1)
    assert len(cals) == 1
    c = cals[0]
    assert c.timeframe == "1h" and c.trades == 1  # unverified excluded
    assert c.win_rate == 1.0
    assert c.expectancy == 10.0


# ── Trust gate: PRIOR until enough verified evidence ──────────────────────────

def test_trust_gate_prior_until_min_trades():
    outs = [_oc("1d", 5.0) for _ in range(3)]
    assert tc.per_timeframe_calibration(outs, min_trades=5)[0].trust == "PRIOR"
    outs += [_oc("1d", 5.0) for _ in range(2)]  # now 5
    assert tc.per_timeframe_calibration(outs, min_trades=5)[0].trust == "CALIBRATED"


def test_win_rate_and_expectancy():
    outs = [_oc("4h", 30.0), _oc("4h", -10.0), _oc("4h", 20.0), _oc("4h", -40.0)]
    c = tc.per_timeframe_calibration(outs, min_trades=1)[0]
    assert c.win_rate == 0.5            # 2 wins / 4
    assert c.expectancy == 0.0          # (30 - 10 + 20 - 40) / 4
    assert c.strategy == "intraday"


def test_strategy_mapping_per_entry_tf():
    cals = tc.per_timeframe_calibration(
        [_oc("15m", 1.0), _oc("1h", 1.0), _oc("4h", 1.0), _oc("1d", 1.0), _oc("1w", 1.0)],
        min_trades=1,
    )
    assert {c.timeframe: c.strategy for c in cals} == {
        "15m": "scalp", "1h": "intraday", "4h": "intraday", "1d": "swing", "1w": "bias_only",
    }


# ── Report: PRIOR from config, trust verdict ──────────────────────────────────

def test_calibration_report_uses_config_prior_and_is_untrusted_early():
    rep = tc.calibration_report([_oc("1h", 5.0) for _ in range(3)], min_trades=10)
    assert rep["min_trades_per_tf"] == 10
    assert rep["tf_weights_trusted"] is False        # 3 < 10 → don't trust yet
    assert rep["calibrated_timeframes"] == []
    # step-8 PRIOR block in weights_v1.0.yaml
    assert "intraday" in rep["tf_weights_prior"]
    assert rep["tf_weights_prior"]["scalp"]["m15"] == 0.50


def test_calibration_report_trusted_once_calibrated():
    rep = tc.calibration_report([_oc("1d", 5.0) for _ in range(4)], min_trades=3)
    assert rep["tf_weights_trusted"] is True
    assert rep["calibrated_timeframes"] == ["1d"]


def test_empty_is_safe():
    assert tc.per_timeframe_calibration([], min_trades=1) == []
    rep = tc.calibration_report([], min_trades=1)
    assert rep["per_timeframe"] == []
    assert rep["tf_weights_trusted"] is False


# ── B5: trust gate POZİTİF beklenti de ister (yeterli örnek tek başına yetmez) ──

def test_negative_expectancy_calibrated_but_not_trusted():
    """Bol örnek + negatif expectancy → CALIBRATED (yeterli veri) ama canlı kapı
    KAPALI (kanıtlı pozitif kenar yok). Eski bug: kaybeden TF güvenilir sayılıyordu."""
    # 4 işlem, net negatif: (10 - 30 + 10 - 30)/4 = -10
    outs = [_oc("1h", 10.0), _oc("1h", -30.0), _oc("1h", 10.0), _oc("1h", -30.0)]
    rep = tc.calibration_report(outs, min_trades=3)
    # per-TF damgası hâlâ CALIBRATED (trainer down-weight edebilsin diye)
    assert rep["calibrated_timeframes"] == ["1h"]
    # ama canlı tf_weights kapısı açılmaz:
    assert rep["tf_weights_trusted"] is False
    assert rep["edge_proven_timeframes"] == []


def test_zero_expectancy_is_not_a_proven_edge():
    """Tam başabaş (expectancy == 0) kanıtlı kenar SAYILMAZ → kapı kapalı."""
    outs = [_oc("4h", 20.0), _oc("4h", -20.0), _oc("4h", 20.0), _oc("4h", -20.0)]
    rep = tc.calibration_report(outs, min_trades=3)
    assert rep["calibrated_timeframes"] == ["4h"]
    assert rep["tf_weights_trusted"] is False


def test_positive_expectancy_opens_gate():
    """Yeterli örnek + pozitif expectancy → kapı açık (B5 regresyon karşıtı)."""
    outs = [_oc("1d", 5.0) for _ in range(4)]
    rep = tc.calibration_report(outs, min_trades=3)
    assert rep["tf_weights_trusted"] is True
    assert rep["edge_proven_timeframes"] == ["1d"]


# ── Denetim 2026-07-03: TF_CALIBRATION_AUTO_ONLY flag'i ───────────────────────
# Bulgu: owner_manual kayıtlar verified olabildiği için TF kalibrasyonuna
# sızıyordu. Flag ON → fingerprint'siz (auto olmayan) verified kayıt kalibre etmez.

def _oc_fp(tf: str, pnl: float, fingerprint: str | None) -> CanonicalOutcome:
    import dataclasses

    return dataclasses.replace(_oc(tf, pnl, verified=True), fingerprint=fingerprint)


def test_flag_off_manual_verified_still_calibrates(monkeypatch):
    """Default (OFF) davranış bayt-aynı: verified yeter, fingerprint aranmaz."""
    monkeypatch.delenv("TF_CALIBRATION_AUTO_ONLY", raising=False)
    outs = [_oc_fp("1d", 10.0, "sig|mod"), _oc_fp("1d", -14.0, None)]
    c = tc.per_timeframe_calibration(outs, min_trades=1)[0]
    assert c.trades == 2


def test_flag_on_excludes_fingerprintless(monkeypatch):
    monkeypatch.setenv("TF_CALIBRATION_AUTO_ONLY", "1")
    outs = [_oc_fp("1d", 10.0, "sig|mod"), _oc_fp("1d", -14.0, None)]
    c = tc.per_timeframe_calibration(outs, min_trades=1)[0]
    assert c.trades == 1
    assert c.expectancy == 10.0
