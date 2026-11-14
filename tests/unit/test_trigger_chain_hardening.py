"""Skor → karar → açılış zincirinin sağlamlık testleri (2026-11-13 düzeltmeleri).

Ortak tema: bozuk ya da eksik girdi sessizce "en güçlü sinyal / en büyük boyut /
kapı açık" sonucuna dönüşmemeli.

- Sayı olmayan (NaN/inf) boyut çarpanı en büyük pozisyonu açıyordu.
- Sayı olmayan modül skoru konsensüsü 100'e (en güçlü yükseliş) çekiyordu.
- Sayı olmayan DQS/equity RiskGate'in bütün denetimlerinden geçiyordu.
- Bozuk fren dosyası "aktif fren yok" okunuyordu; dosya atomik yazılmıyordu.
- "Son işlemler zarardaysa yarım boy" freni canlı yolda (decide_matrix) hiç çalışmıyordu.
- Son kapıda düşecek aday, aynı sembolün diğer zaman dilimlerini boşuna bekletiyordu.
- Eğimi ters çıkan olasılık eğrisi "uydurulmuş" sayılıp karara giriyordu.
"""
from __future__ import annotations

import importlib
import json
import math
from types import SimpleNamespace

import pytest

NAN = float("nan")
INF = float("inf")


# ───────────────────────────── boyut hesabı ─────────────────────────────

@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_compute_size_usd_non_finite_multiplier_opens_nothing(bad) -> None:
    from packages.paper import sizing

    assert sizing.compute_size_usd(bad, max_position_usd=25_000.0) == 0.0


def test_compute_size_usd_non_finite_cap_opens_nothing() -> None:
    from packages.paper import sizing

    assert sizing.compute_size_usd(1.0, max_position_usd=NAN) == 0.0
    assert sizing.compute_size_usd(1.0, max_position_usd=INF) == 0.0


def test_compute_size_usd_normal_values_unchanged() -> None:
    from packages.paper import sizing

    assert sizing.compute_size_usd(1.0, max_position_usd=25_000.0) == 25_000.0
    assert sizing.compute_size_usd(9.0, max_position_usd=25_000.0) == 37_500.0  # tavan 1,5×
    assert sizing.compute_size_usd(-1.0, max_position_usd=25_000.0) == 0.0


def test_ai_multiplier_non_finite_reduces_to_zero() -> None:
    from packages.paper import sizing

    assert sizing.clamp_ai_multiplier(NAN) == 0.0
    assert sizing.clamp_ai_multiplier(INF) == 0.0
    assert sizing.clamp_ai_multiplier(None) == 1.0
    assert sizing.apply_ai_opinion(NAN, None) == 0.0
    assert sizing.apply_ai_opinion(1.2, 0.5) == pytest.approx(0.6)


def test_attempt_open_rejects_non_finite_multiplier(tmp_path, monkeypatch) -> None:
    """Uçtan uca: NaN çarpanla açılış denemesi pozisyon açmaz (eskiden 37.500 $)."""
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    from packages.paper import lifecycle
    from packages.paper import state as ps

    importlib.reload(ps)
    monkeypatch.setattr(lifecycle.price_sanity, "price_sane_with_ohlcv_reason", lambda *a, **k: None)
    state = ps.PaperState(equity_usd=100_000.0, peak_equity_usd=100_000.0)
    pos, decision = lifecycle.attempt_open(
        state, symbol="BTCUSD", side="long", entry_price=60_000.0, size_multiplier=NAN,
    )
    assert pos is None
    assert decision["reason"] == "zero_size"
    assert state.open_positions == []


# ───────────────────────────── karar motoru ─────────────────────────────

@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    monkeypatch.setenv("GUARD_OVERRIDES_PATH", str(tmp_path / "guard_overrides.json"))
    from packages.paper import state as ps

    importlib.reload(ps)
    return ps


def _force_pass(monkeypatch, *, score: float = 85.0):
    from packages.consensus.engine import ConsensusResult, ModuleScore
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.decision import engine as dec
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    fake = ConsensusResult(
        symbol="BTCUSD", score=score, direction="bullish", confluence_aligned=True,
        dominant_module="touche",
        modules=[ModuleScore(name="touche", score=score, weight=1.0, contribution=score)],
    )
    monkeypatch.setattr(dec, "build_consensus", lambda *a, **kw: fake)
    return dec, snap, regime


def _hold_risk():
    from packages.risk.engine import RiskDecision

    return RiskDecision(action="HOLD", reason="ok", evidence=[])


def test_bounded_size_keeps_nan_visible() -> None:
    from packages.decision import engine as dec

    assert math.isnan(dec._bounded_size(NAN))
    assert math.isnan(dec._bounded_size(INF))
    assert dec._bounded_size(9.0) == 1.5
    assert dec._bounded_size(-1.0) == 0.0


def test_engine_baseline_candidate_opens(fresh_env, monkeypatch) -> None:
    """Kontrol: aynı kurulum bozuk çarpan olmadan açılış üretir."""
    dec, snap, regime = _force_pass(monkeypatch)
    d = dec.decide_for_symbol("BTCUSD", snap, regime, _hold_risk(), equity_usd=100_000)
    assert d.action == "open_long"
    assert d.size_multiplier > 0.0


def test_engine_nan_regime_multiplier_blocks_instead_of_max_size(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec, "_regime_multiplier", lambda label: NAN)
    d = dec.decide_for_symbol("BTCUSD", snap, regime, _hold_risk(), equity_usd=100_000)
    assert d.action == "hold"
    assert d.size_multiplier == 0.0
    assert "sizing_fault:non_finite" in d.blocked_by
    assert d.actionable is False


def test_engine_nan_restrictor_is_not_silently_ignored(fresh_env, monkeypatch) -> None:
    """Kısıtlayıcı çarpan NaN ise `min(1.0, NaN)` onu yok sayardı (kısma uygulanmazdı)."""
    dec, snap, regime = _force_pass(monkeypatch)
    from packages.learning.mistake_memory import MistakeVerdict

    broken = MistakeVerdict(action="WARNING", reason="t", size_factor=NAN, evidence=[], fingerprint="x")
    monkeypatch.setattr(dec.mistake_memory, "evaluate", lambda fp, mems=None: broken)
    d = dec.decide_for_symbol("BTCUSD", snap, regime, _hold_risk(), equity_usd=100_000)
    assert d.action == "hold"
    assert "sizing_fault:non_finite" in d.blocked_by


def test_engine_nan_expected_value_is_blocked_by_ev_gate(fresh_env, monkeypatch) -> None:
    dec, snap, regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec, "_cost_r", lambda *a, **k: NAN)
    d = dec.decide_for_symbol("BTCUSD", snap, regime, _hold_risk(), equity_usd=100_000)
    assert d.action == "hold"
    assert d.blocked_by == ["ev_gate"]


def test_decide_matrix_applies_recent_edge_brake(fresh_env, monkeypatch) -> None:
    """Canlı yol: decide_matrix son işlemlerin edge'ini okur ve freni uygular."""
    dec, snap, _regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec, "_recent_edge", lambda lookback: -0.4)
    from packages.risk.engine import RiskInput

    risk_in = RiskInput(dqs_score=90.0, equity_usd=100_000.0, peak_equity_usd=100_000.0,
                        daily_pnl_usd=0.0, open_position_count=0)
    _r, _risk, decisions = dec.decide_matrix(["BTCUSD"], snap, risk_in, timeframes=["1h"])
    (d,) = decisions
    assert d.sizing_layers_report["brake"]["recent_edge"] == -0.4
    assert d.sizing_layers_report["brake"]["factor"] == 0.5


def test_decide_matrix_no_brake_without_evidence(fresh_env, monkeypatch) -> None:
    dec, snap, _regime = _force_pass(monkeypatch)
    monkeypatch.setattr(dec, "_recent_edge", lambda lookback: None)
    from packages.risk.engine import RiskInput

    risk_in = RiskInput(dqs_score=90.0, equity_usd=100_000.0, peak_equity_usd=100_000.0,
                        daily_pnl_usd=0.0, open_position_count=0)
    _r, _risk, decisions = dec.decide_matrix(["BTCUSD"], snap, risk_in, timeframes=["1h"])
    (d,) = decisions
    assert d.sizing_layers_report["brake"]["factor"] == 1.0


# ───────────── kardeş hücre: açılamayacak aday yer tutmaz ─────────────

def _signal(name: str, direction: str):
    return SimpleNamespace(name=name, direction=direction, fired=direction == "bullish")


def _snap_with(signals, status: str = "OK"):
    tech = SimpleNamespace(status=status, confirmation_signals=signals)
    return SimpleNamespace(technicals_by_tf={"BTCUSD": {"1h": tech}}, technicals={})


def _candidate(*, actionable: bool = True, ev: float | None = 0.2):
    return SimpleNamespace(
        symbol="BTCUSD", timeframe="1h", action="open_short", actionable=actionable,
        expected_value=ev, size_multiplier=0.5,
    )


def test_reaches_paper_route_requires_confirmation_groups() -> None:
    from packages.decision import engine as dec

    confirmed = _snap_with([
        _signal("macd_histogram_positive", "bearish"), _signal("ema_stack_bullish", "bearish"),
    ])
    momentum_only = _snap_with([
        _signal("macd_histogram_positive", "bearish"), _signal("rsi_above_50", "bearish"),
        _signal("ema_stack_bullish", "neutral"),
    ])
    assert dec._reaches_paper_route(_candidate(), confirmed) is True
    assert dec._reaches_paper_route(_candidate(), momentum_only) is False


def test_reaches_paper_route_requires_ready_data_and_execution() -> None:
    from packages.decision import engine as dec

    signals = [_signal("macd_histogram_positive", "bearish"), _signal("ema_stack_bullish", "bearish")]
    assert dec._reaches_paper_route(_candidate(), _snap_with(signals, status="DEGRADED")) is False
    assert dec._reaches_paper_route(_candidate(actionable=False), _snap_with(signals)) is False
    assert dec._reaches_paper_route(_candidate(ev=-0.1), _snap_with(signals)) is False


# ───────────────────────────── konsensüs ─────────────────────────────

def test_oriented_does_not_turn_nan_into_100() -> None:
    from packages.consensus import engine as ce

    assert math.isnan(ce._oriented("sentinel", NAN, "BTCUSD", "1h"))
    assert 0.0 <= ce._oriented("sentinel", 80.0, "BTCUSD", "1h") <= 100.0


def test_consensus_drops_non_finite_module_instead_of_max_bullish(monkeypatch) -> None:
    from packages.consensus import engine as ce
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    ctx = {"fundamental": 50.0, "sentinel": 50.0}
    monkeypatch.setattr(ce, "_context_layer", lambda *_a, **_k: (dict(ctx), dict(ctx)))
    monkeypatch.setattr(ce, "_touche", lambda *_a, **_k: (NAN, []))
    res = ce.build("BTCUSD", snap, regime, "1h")
    assert math.isfinite(res.score)
    assert res.score < 55.0                       # eskiden 100,0 (en güçlü yükseliş)
    assert res.direction != "bullish"
    assert all(m.name != "touche" for m in res.modules)
    assert any(w.startswith("module_non_finite:touche") for w in res.warnings)


def test_consensus_non_finite_module_is_missing_data_under_live_policy(monkeypatch) -> None:
    """Canlı politika: verisi gelmeyen modül nötr doldurulur ve hücre nötre zorlanır."""
    from packages.consensus import engine as ce
    from packages.data.ingestion.pipeline import build_snapshot
    from packages.regime.classifier import classify

    snap = build_snapshot(["BTCUSD"])
    regime = classify(snap)
    ctx = {"fundamental": 90.0, "sentinel": 90.0}
    monkeypatch.setattr(ce, "_context_layer", lambda *_a, **_k: (dict(ctx), dict(ctx)))
    monkeypatch.setattr(ce, "_touche", lambda *_a, **_k: (NAN, []))
    monkeypatch.setattr(ce, "_strict_missing_modules_active", lambda generated_at: True)
    res = ce.build("BTCUSD", snap, regime, "1h")
    assert res.direction == "neutral"
    assert any(w.startswith("coverage_gate:forced_neutral") for w in res.warnings)


def test_sentinel_v2_ignores_non_finite_volatility(monkeypatch) -> None:
    from packages.consensus import engine as ce

    regime = SimpleNamespace(layers=[SimpleNamespace(name="Risk İştahı", score=40.0)], label="NEUTRAL")
    vol = SimpleNamespace(status="OK", verified=True, vol_zscore=NAN, vol_state="normal")
    snap = SimpleNamespace(volatility={"BTCUSD": {"1h": vol}}, derivatives={}, options={})
    # Bozuk oynaklık girdisi "çok sakin" (100) sayılmaz; yalnız VIX katmanı kalır.
    assert ce._sentinel_v2(regime, snap, "BTCUSD", "1h") == pytest.approx(40.0)


# ───────────────────────────── RiskGate ─────────────────────────────

def _risk_input(**over):
    from packages.risk.engine import RiskInput

    base = {"dqs_score": 90.0, "equity_usd": 100_000.0, "peak_equity_usd": 100_000.0,
            "daily_pnl_usd": 0.0, "open_position_count": 0}
    base.update(over)
    return RiskInput(**base)


@pytest.mark.parametrize("field", ["dqs_score", "equity_usd", "peak_equity_usd", "daily_pnl_usd"])
def test_risk_gate_closes_on_non_finite_input(field) -> None:
    from packages.risk.engine import evaluate

    res = evaluate(_risk_input(**{field: NAN}))
    assert res.action == "KILL_SWITCH"
    assert any(field in line for line in res.evidence)


def test_risk_gate_closes_on_non_finite_mtm() -> None:
    from packages.risk.engine import evaluate

    assert evaluate(_risk_input(mtm_equity_usd=NAN)).action == "KILL_SWITCH"
    assert evaluate(_risk_input(mtm_equity_usd=None)).action == "HOLD"


def test_risk_gate_normal_inputs_unchanged() -> None:
    from packages.risk.engine import evaluate

    assert evaluate(_risk_input()).action == "HOLD"
    assert evaluate(_risk_input(dqs_score=40.0)).action == "KILL_SWITCH"


# ───────────────────────────── fren deposu ─────────────────────────────

@pytest.fixture
def halt_env(tmp_path, monkeypatch):
    path = tmp_path / "risk_halts.json"
    monkeypatch.setenv("RISK_HALT_PATH", str(path))
    from packages.risk import halt

    return halt, path


def test_corrupt_halt_file_is_not_read_as_no_halt(halt_env) -> None:
    halt, path = halt_env
    path.write_text('{"events": [{"id": "max_drawdown-x", "type": "MAX_DRAW', encoding="utf-8")
    state = halt.load()
    assert state.unreadable is True
    active = halt.active_halts()
    assert [e.type for e in active] == [halt.STORE_UNREADABLE]
    assert active[0].level == "RISK_REDUCE"


def test_wrong_shape_halt_file_is_unreadable(halt_env) -> None:
    halt, path = halt_env
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert halt.load().unreadable is True


def test_missing_halt_file_is_a_clean_first_run(halt_env) -> None:
    halt, _path = halt_env
    assert halt.load().unreadable is False
    assert halt.active_halts() == []


def test_risk_gate_restricts_while_halt_file_unreadable(halt_env) -> None:
    _halt, path = halt_env
    path.write_text("{not json", encoding="utf-8")
    from packages.risk.engine import evaluate

    res = evaluate(_risk_input())
    assert res.action == "RISK_REDUCE"


def test_sync_quarantines_corrupt_file_and_rebuilds_active_halts(halt_env) -> None:
    halt, path = halt_env
    path.write_text("{not json", encoding="utf-8")
    # Düşüş koşulu sürüyor (%10) → fren yeniden kurulur.
    active = halt.sync(_risk_input(equity_usd=90_000.0))
    assert [e.type for e in active] == ["MAX_DRAWDOWN"]
    assert active[0].level == "KILL_SWITCH"
    assert json.loads(path.read_text(encoding="utf-8"))["events"][0]["type"] == "MAX_DRAWDOWN"
    assert halt.load().unreadable is False
    assert list(path.parent.glob("risk_halts.json.corrupt-*")), "bozuk dosya incelenmek üzere saklanmalı"


def test_sync_after_corruption_without_breach_writes_clean_file(halt_env) -> None:
    halt, path = halt_env
    path.write_text("{not json", encoding="utf-8")
    assert halt.sync(_risk_input()) == []
    assert json.loads(path.read_text(encoding="utf-8")) == {"events": []}
    assert halt.active_halts() == []


def test_halt_save_is_atomic(halt_env, monkeypatch) -> None:
    """Yazma yarıda kalırsa eski, geçerli dosya yerinde kalır."""
    halt, path = halt_env
    halt.sync(_risk_input(equity_usd=90_000.0))
    before = path.read_text(encoding="utf-8")
    from packages.ops import store

    def boom(src, dst):
        raise OSError("disk dolu")

    monkeypatch.setattr(store, "replace_with_retry", boom)
    with pytest.raises(OSError):
        halt.save(halt.HaltState())
    assert path.read_text(encoding="utf-8") == before
    assert not list(path.parent.glob(".risk_halts.json.*.tmp"))


# ───────────────────────────── kalibrasyon ─────────────────────────────

@pytest.fixture
def cal_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIBRATION_STORE_PATH", str(tmp_path / "platt.json"))
    from packages.learning import calibration_store

    return calibration_store


def _inverted_samples(n: int = 14) -> list[tuple[str, float, bool]]:
    # Güçlü sinyal kaybediyor, zayıf sinyal kazanıyor → Platt eğimi negatif.
    out = []
    for i in range(n):
        strong = i % 2 == 0
        out.append(("1d", 0.8 if strong else 0.2, not strong))
    return out


def test_inverted_fit_is_rejected_per_timeframe(cal_env, monkeypatch) -> None:
    from packages.learning import calibration_trainer as trainer

    monkeypatch.setattr(trainer, "_samples_from_state", lambda: _inverted_samples())
    summary = trainer.train()
    assert summary["per_timeframe"]["1d"]["status"] == "insufficient"
    assert summary["rejected_fits"]["1d"]["reason"] == "non_positive_slope"
    assert summary["rejected_fits"]["1d"]["a"] < 0
    assert "1d" not in summary["tf_fitted"]
    # Küresel fit de aynı örneklerden ters çıkar → o da kullanılmaz.
    assert summary["status"] == "INSUFFICIENT"
    assert cal_env.predict_calibrated_tf(0.4, "1d") == (0.4, "insufficient")


def test_normal_fit_still_accepted(cal_env, monkeypatch) -> None:
    from packages.learning import calibration_trainer as trainer

    samples = [("1h", 0.8, True)] * 9 + [("1h", 0.8, False)] * 3 + \
              [("1h", 0.2, True)] * 4 + [("1h", 0.2, False)] * 8
    monkeypatch.setattr(trainer, "_samples_from_state", lambda: samples)
    summary = trainer.train()
    assert summary["status"] == "FITTED"
    assert summary["per_timeframe"]["1h"]["status"] == "fitted"
    assert summary["rejected_fits"] == {}
    strong, _ = cal_env.predict_calibrated_tf(0.8, "1h")
    weak, _ = cal_env.predict_calibrated_tf(0.2, "1h")
    assert strong > weak


def test_stored_inverted_fit_is_ignored_at_read_time(cal_env) -> None:
    """Diskte eski sürümün yazdığı ters eğimli fit varsa karar onu kullanmaz."""
    good = cal_env.CalibrationParams(a=0.3, b=0.4, samples=149, fitted_at="t", status="fitted")
    bad = cal_env.CalibrationParams(a=-0.24, b=1.34, samples=14, fitted_at="t", status="fitted")
    cal_env.save(good, per_timeframe={"1d": bad})
    value, source = cal_env.predict_calibrated_tf(0.5, "1d")
    assert source == "fitted"                      # küresel fit'e düştü
    assert value == cal_env.predict_calibrated(0.5)[0]
    cal_env.save(bad, per_timeframe={})
    assert cal_env.predict_calibrated(0.5) == (0.5, "insufficient")
