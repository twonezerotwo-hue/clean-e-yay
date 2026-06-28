"""TF-target trainer + store unit tests.

Trainer kapanmış paper trade'lerden TF başına SL/TP nudge üretir.
Store hibrit uygular: ±AUTO_APPLY_BAND_PCT içi auto, dışı PENDING.
Mutlak guardrail clamp her zaman zorlanır.
"""
from __future__ import annotations

import os

import pytest

from packages.learning import tf_target_store as store
from packages.learning import tf_target_trainer as trainer


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """İzole tf_targets.json — gerçek runtime dosyasına dokunma."""
    monkeypatch.setenv("TF_TARGET_STORE_PATH", str(tmp_path / "tf_targets.json"))
    store.reset()
    return tmp_path


# ── Store: hibrit auto-apply ──────────────────────────────────────────────────

def test_within_band_auto_applies(isolated_store):
    """Mevcut değerin ±%15 bandındaki öneri AUTO_APPLIED."""
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    proposal = {
        "generated_at": "now",
        "per_timeframe": {"1h": {"sl_atr_mult": 1.3, "rr": 1.85, "sl_pct_floor": 0.011, "sl_pct_cap": 0.036}},
    }
    rec = store.submit_proposal(proposal, current_baseline=baseline)
    assert rec["decisions"]["1h"].startswith("auto_applied")
    assert store.active_overrides()["1h"]["sl_atr_mult"] == 1.3
    assert store.get_pending() is None


def test_out_of_band_pending(isolated_store):
    """Bandın dışı PENDING (owner onayı bekler), current değişmez."""
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    proposal = {
        "generated_at": "now",
        "per_timeframe": {"1h": {"sl_atr_mult": 2.5, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}},
    }
    rec = store.submit_proposal(proposal, current_baseline=baseline)
    assert rec["decisions"]["1h"].startswith("pending")
    assert store.active_overrides() == {}  # current değişmedi
    assert store.get_pending() is not None


def test_approve_pending_applies(isolated_store):
    """approve_pending: bekleyen değişiklikleri current'a yazar."""
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    store.submit_proposal(
        {"generated_at": "now",
         "per_timeframe": {"1h": {"sl_atr_mult": 2.5, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}},
        current_baseline=baseline,
    )
    ap = store.approve_pending()
    assert ap is not None and ap["status"] == "APPROVED"
    assert store.active_overrides()["1h"]["sl_atr_mult"] == 2.5
    assert store.get_pending() is None


def test_reject_pending_keeps_current(isolated_store):
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    store.submit_proposal(
        {"generated_at": "now",
         "per_timeframe": {"1h": {"sl_atr_mult": 2.5, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}},
        current_baseline=baseline,
    )
    rj = store.reject_pending("test")
    assert rj is not None and rj["status"] == "REJECTED"
    assert store.active_overrides() == {}
    assert store.get_pending() is None


def test_guardrail_clamps_extreme_values(isolated_store):
    """sl_atr_mult > 3.0 olsa bile clamp 3.0'a kıstırır (kötü öneri güvenli)."""
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    store.submit_proposal(
        {"generated_at": "now",
         "per_timeframe": {"1h": {"sl_atr_mult": 99.0, "rr": 1.85, "sl_pct_floor": 0.011, "sl_pct_cap": 0.036}}},
        current_baseline=baseline,
    )
    # sl_atr_mult 99 → bandın dışı → pending; ama approve edersek clamp 3.0
    ap = store.approve_pending()
    assert ap is not None
    assert store.active_overrides()["1h"]["sl_atr_mult"] == 3.0  # clamped


def test_empty_store_no_override(isolated_store):
    """Boş store → active_overrides {} → compute_tf_targets saf config kullanır."""
    assert store.active_overrides() == {}


# ── Trainer: dataset filtering + nudge rules ──────────────────────────────────

class _FakeOutcome:
    """outcomes_from_state'in döndürdüğüne benzer minimal mock."""
    def __init__(self, *, timeframe, pnl, close_reason, mae_pct, mfe_pct, verified=True):
        self.timeframe = timeframe
        self.pnl = pnl
        self.close_reason = close_reason
        self.mae_pct = mae_pct
        self.mfe_pct = mfe_pct
        self.data_verified = verified


def test_trainer_insufficient_when_no_verified(monkeypatch):
    """0 verified outcome → INSUFFICIENT dict."""
    monkeypatch.setattr(trainer.paper_state, "load", lambda: type("S", (), {"recent_trades": []})())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: [])
    r = trainer.train()
    assert isinstance(r, dict)
    assert r["status"] == "INSUFFICIENT"


def test_trainer_skips_tf_with_low_sample(monkeypatch):
    """Bir TF MIN_TRADES_PER_TF altındaysa skipped'e düşer (nudge yok)."""
    rows = [
        _FakeOutcome(timeframe="1h", pnl=10, close_reason="TP", mae_pct=0.3, mfe_pct=2.0)
        for _ in range(5)
    ]
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: rows)
    p = trainer.train(timeframes=["1h"])
    assert "1h" in p.skipped
    assert "insufficient" in p.skipped["1h"]
    assert p.per_timeframe == {}


def test_trainer_nudges_sl_when_too_tight(monkeypatch):
    """SL-hit yüksek + MAE düşük → sl_atr_mult ↑ (Kural 1)."""
    # 20 trade, 12'si SL-hit (60% > 45% eşik), MAE düşük (typical SL'in çok altı).
    # Default 1h baseline: sl_pct_floor 0.010, sl_pct_cap 0.035 → typical 2.25%
    # MAE 0.3% → ratio 0.13 < 0.50 → nudge tetiklenir.
    rows = []
    for _ in range(12):
        rows.append(_FakeOutcome(timeframe="1h", pnl=-5, close_reason="SL",
                                 mae_pct=0.3, mfe_pct=0.2))
    for _ in range(8):
        rows.append(_FakeOutcome(timeframe="1h", pnl=5, close_reason="TP",
                                 mae_pct=0.3, mfe_pct=2.0))
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: rows)
    p = trainer.train(timeframes=["1h"], store_overrides={})
    nudge_params = [n.param for n in p.nudges]
    assert "sl_atr_mult" in nudge_params
    sl_nudge = next(n for n in p.nudges if n.param == "sl_atr_mult")
    assert sl_nudge.new > sl_nudge.old
    assert "sl_atr_mult" in p.per_timeframe["1h"]


def test_trainer_nudges_rr_down_when_tp_unreachable(monkeypatch):
    """TP-hit düşük + time-stop yüksek + MFE düşük → rr ↓ (Kural 2)."""
    # Default 1h rr=1.8, typical_tp ≈ 4.05%. MFE 0.5% → ratio ≈0.12 < 0.50.
    rows = []
    for _ in range(2):  # 10% TP-hit < 25%
        rows.append(_FakeOutcome(timeframe="1h", pnl=5, close_reason="TP",
                                 mae_pct=0.8, mfe_pct=0.5))
    for _ in range(10):  # 50% time-stop > 30%
        rows.append(_FakeOutcome(timeframe="1h", pnl=-1, close_reason="TIME_STOP_EXIT",
                                 mae_pct=0.8, mfe_pct=0.5))
    for _ in range(8):  # geri kalanı SL
        rows.append(_FakeOutcome(timeframe="1h", pnl=-5, close_reason="SL",
                                 mae_pct=1.5, mfe_pct=0.5))
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: rows)
    p = trainer.train(timeframes=["1h"], store_overrides={})
    rr_nudges = [n for n in p.nudges if n.param == "rr"]
    assert len(rr_nudges) == 1
    assert rr_nudges[0].new < rr_nudges[0].old


def test_trainer_no_nudge_when_in_band(monkeypatch):
    """Sağlıklı dağılım (eşikleri tetiklemeyen) → 0 nudge."""
    rows = []
    for _ in range(10):
        rows.append(_FakeOutcome(timeframe="1h", pnl=5, close_reason="TP",
                                 mae_pct=1.0, mfe_pct=2.0))
    for _ in range(10):
        rows.append(_FakeOutcome(timeframe="1h", pnl=-3, close_reason="SL",
                                 mae_pct=2.0, mfe_pct=0.5))
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: rows)
    p = trainer.train(timeframes=["1h"], store_overrides={})
    assert p.nudges == []
    assert p.per_timeframe == {}  # öneri yok


def test_unverified_outcomes_excluded(monkeypatch):
    """data_verified=False outcome'lar dataset'e girmez."""
    rows = [
        _FakeOutcome(timeframe="1h", pnl=10, close_reason="TP",
                     mae_pct=0.5, mfe_pct=2.0, verified=False)
        for _ in range(50)
    ]
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state", lambda s: rows)
    r = trainer.train(timeframes=["1h"])
    assert isinstance(r, dict) and r["status"] == "INSUFFICIENT"


# ── Loop: trainer → store → effective params ──────────────────────────────────

def test_effective_params_use_store_override(isolated_store):
    """compute_tf_targets._tf_params store override'larını okur."""
    from packages.risk.trade_economics import _tf_params
    baseline_15m = _tf_params("15m")  # store boş → defaults
    # Store'a override yaz
    store.submit_proposal(
        {"generated_at": "now",
         "per_timeframe": {"15m": {"sl_atr_mult": 1.05, "rr": 1.5, "sl_pct_floor": 0.005, "sl_pct_cap": 0.020}}},
        current_baseline={"15m": baseline_15m},
    )
    after = _tf_params("15m")
    assert after["sl_atr_mult"] == 1.05  # store override etkili
