"""TF-target trainer + store unit tests.

Trainer kapanmış paper trade'lerden TF başına SL/TP nudge üretir.
Store hibrit uygular: ±AUTO_APPLY_BAND_PCT içi auto, dışı PENDING.
Mutlak guardrail clamp her zaman zorlanır.
"""
from __future__ import annotations


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


# ── Worker integration: trigger gate ─────────────────────────────────────────

def test_worker_gate_pending_no_new_outcomes(tmp_path, monkeypatch):
    """İkinci koşuda (outcome sayısı değişmediyse) GATE_PENDING dönmeli."""
    monkeypatch.setenv("TF_TARGET_STORE_PATH", str(tmp_path / "tf_targets.json"))
    monkeypatch.setenv("TF_TARGET_TRIGGER_PATH", str(tmp_path / "trigger.json"))
    monkeypatch.setenv("TF_TARGET_PROPOSAL_OUT_PATH", str(tmp_path / "prop.json"))
    # Re-import so module-level Path() pick up the env.
    import importlib
    import apps.learning_worker.main as lw
    importlib.reload(lw)
    # First run primes the trigger file.
    r1 = lw.run_once()
    assert r1.get("tf_target_status") in ("NO_NUDGE", "PROPOSED", "INSUFFICIENT")
    # Second run — outcomes_seen aynıysa kapı kapalı.
    r2 = lw.run_once()
    assert r2.get("tf_target_status", "").startswith("GATE_PENDING")


def test_classify_close_matches_live_reason_strings() -> None:
    """Bugfix 2026-07-03: canlı close_reason'lar SL_HIT/TP_HIT — eski eşleme
    bunları 'other'a düşürüyordu (sl_hit/tp_hit sayaçları hep 0 kalıyordu)."""
    from packages.learning.tf_target_trainer import _classify_close
    assert _classify_close("SL_HIT") == "sl"
    assert _classify_close("TP_HIT") == "tp"
    assert _classify_close("SL") == "sl"          # legacy string de çalışır
    assert _classify_close("TP") == "tp"
    assert _classify_close("TIME_STOP_EXIT") == "time_stop"
    assert _classify_close("TRAILING_STOP_EXIT") == "trailing"
    assert _classify_close("MANUAL") == "other"
    assert _classify_close("KILL_SWITCH_EXIT") == "other"
    assert _classify_close(None) == "other"


# ── Dilim 4: TF_TARGET_AUTO_ONLY (girdi hijyeni) ─────────────────────────────

def _mk_outcome(i: int, *, fingerprint, open_reason, verified=True):
    from packages.learning.outcomes import CanonicalOutcome
    return CanonicalOutcome(
        trade_id=f"t{i}", symbol="BTCUSD", timeframe="1h",
        opened_at=None, closed_at=None, duration_seconds=None,
        direction="long", open_price=100.0, close_price=101.0,
        pnl=10.0, pnl_pct=1.0, open_reason=open_reason,
        close_reason="TP_HIT", fingerprint=fingerprint, regime="NEUTRAL",
        dominant_module="touche", candidate_action="open_long",
        final_action="open_long", data_verified=verified,
        mae_pct=0.2, mfe_pct=1.5,
    )


def _mixed_rows():
    fp = "BTCUSD|v2|1h|NEUTRAL|bullish|S55|C|touche"
    auto = [_mk_outcome(i, fingerprint=fp, open_reason="signal") for i in range(25)]
    manual = [_mk_outcome(100 + i, fingerprint=None, open_reason="owner_manual")
              for i in range(10)]  # verified ama fingerprint'siz → AUTO değil
    return auto + manual


def test_auto_only_off_uses_all_verified(monkeypatch):
    monkeypatch.delenv("TF_TARGET_AUTO_ONLY", raising=False)
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state",
                        lambda s=None: _mixed_rows())
    monkeypatch.setattr(trainer.paper_state, "load", lambda: None)
    p = trainer.train(timeframes=["1h"])
    assert p.dataset_size == 35  # verified hepsi (manuel dahil) — mevcut davranış
    assert "dataset=verified" in p.audit_note


def test_auto_only_on_excludes_manual_verified(monkeypatch):
    monkeypatch.setenv("TF_TARGET_AUTO_ONLY", "1")
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state",
                        lambda s=None: _mixed_rows())
    monkeypatch.setattr(trainer.paper_state, "load", lambda: None)
    p = trainer.train(timeframes=["1h"])
    assert p.dataset_size == 25  # manuel-verified 10 kayıt dışlandı
    assert "dataset=auto_cohort" in p.audit_note


def test_entry_exit_quality_honors_same_flag(monkeypatch):
    from packages.learning import entry_exit_quality as eeq
    monkeypatch.setattr(eeq.outcomes_mod, "outcomes_from_state",
                        lambda s=None: _mixed_rows())
    monkeypatch.delenv("TF_TARGET_AUTO_ONLY", raising=False)
    assert eeq.report()["total"] == 35
    monkeypatch.setenv("TF_TARGET_AUTO_ONLY", "1")
    assert eeq.report()["total"] == 25


def test_coverage_status_follows_active_flag(monkeypatch):
    """/learning/tf-targets coverage: status trainer'ın FİİLEN kullandığı sayıya
    bakar — flag OFF verified_n (mevcut davranış), ON auto_n (dürüst gösterge)."""
    from apps.api.routers import learning as lr
    fp = "BTCUSD|v2|1h|NEUTRAL|bullish|S55|C|touche"
    rows = (
        [_mk_outcome(i, fingerprint=fp, open_reason="signal") for i in range(15)]
        + [_mk_outcome(100 + i, fingerprint=None, open_reason="owner_manual")
           for i in range(10)]
    )  # auto_n=15 < 20 ≤ verified_n=25 → flag durumu status'u çevirir
    monkeypatch.setattr(lr.outcomes_mod, "outcomes_from_state", lambda s=None: rows)
    monkeypatch.delenv("TF_TARGET_AUTO_ONLY", raising=False)
    assert lr._tf_target_coverage()["1h"]["status"] == "TRAINED"
    monkeypatch.setenv("TF_TARGET_AUTO_ONLY", "1")
    cov = lr._tf_target_coverage()["1h"]
    assert cov["status"] == "UNTRAINED"
    assert cov["auto_n"] == 15 and cov["verified_n"] == 25


# ── Dilim 5: EXIT_FORENSICS_NUDGE (oransal nudge adımı) ──────────────────────

def _stats(**kw):
    base = dict(
        timeframe="1h", trades=20, wins=8, win_rate=0.4,
        sl_hit=12, tp_hit=8, time_stop=0, other_exit=0,
        sl_hit_rate=0.6, tp_hit_rate=0.4, time_stop_rate=0.0,
        avg_mae_pct=0.3, avg_mfe_pct=2.0, avg_pnl=0.0,
    )
    base.update(kw)
    return trainer.TfStats(**base)


def _tight_sl_rows():
    """test_trainer_nudges_sl_when_too_tight ile aynı TIGHT_SL fikstürü."""
    rows = []
    for _ in range(12):
        rows.append(_FakeOutcome(timeframe="1h", pnl=-5, close_reason="SL",
                                 mae_pct=0.3, mfe_pct=0.2))
    for _ in range(8):
        rows.append(_FakeOutcome(timeframe="1h", pnl=5, close_reason="TP",
                                 mae_pct=0.3, mfe_pct=2.0))
    return rows


def test_step_fixed_when_flag_off(monkeypatch):
    """Regresyon bekçisi: flag OFF → forensics kanıtı olsa bile sabit NUDGE_STEP."""
    monkeypatch.delenv("EXIT_FORENSICS_NUDGE", raising=False)
    step, src, ev = trainer._step_for(
        "TIGHT_SL", _stats(), {"sl_roundtrip_share": 1.0}, 0.1)
    assert (step, src, ev) == (trainer.NUDGE_STEP, "fixed", "")
    assert trainer.NUDGE_STEP == 0.10


def test_step_clamped_between_min_and_max(monkeypatch):
    monkeypatch.setenv("EXIT_FORENSICS_NUDGE", "1")
    st = _stats()
    s0, _, _ = trainer._step_for("TIGHT_SL", st, {"sl_roundtrip_share": 0.0}, 0.1)
    assert s0 == trainer.STEP_MIN == 0.05
    s1, _, _ = trainer._step_for("TIGHT_SL", st, {"sl_roundtrip_share": 1.0}, 0.1)
    assert s1 == trainer.STEP_MAX == 0.15
    # Bozuk/aşırı şiddet değeri de klamplanır
    s2, _, _ = trainer._step_for("TIGHT_SL", st, {"sl_roundtrip_share": 5.0}, 0.1)
    assert s2 == 0.15


def test_step_forensics_preferred_stats_fallback(monkeypatch):
    monkeypatch.setenv("EXIT_FORENSICS_NUDGE", "1")
    st = _stats(sl_hit_rate=0.60)
    s_fx, src_fx, ev_fx = trainer._step_for(
        "TIGHT_SL", st, {"sl_roundtrip_share": 0.5}, 0.1)
    assert src_fx == "proportional(forensics)"
    assert "sl_roundtrip_share" in ev_fx
    assert s_fx == 0.10  # 0.05 + 0.10×0.5
    # Forensics kanıtı yok → TfStats fallback (o da ölçüm): (0.60-0.45)/0.30 = 0.5
    s_st, src_st, ev_st = trainer._step_for("TIGHT_SL", st, None, 0.1)
    assert src_st == "proportional(stats)"
    assert "sl_hit_rate" in ev_st
    assert s_st == 0.10


def test_step_trailing_rule_paths(monkeypatch):
    monkeypatch.setenv("EXIT_FORENSICS_NUDGE", "1")
    st = _stats(avg_capture=0.25)
    s_fx, src_fx, _ = trainer._step_for(
        "TRAILING_LOOSE", st, {"trailing_giveback_ratio": 1.0}, 0.1)
    assert (s_fx, src_fx) == (0.15, "proportional(forensics)")
    # Fallback: (0.50-0.25)/0.50 = 0.5 → 0.10
    s_st, src_st, ev = trainer._step_for("TRAILING_LOOSE", st, {}, 0.1)
    assert (s_st, src_st) == (0.10, "proportional(stats)")
    assert "avg_capture" in ev


def test_max_step_stays_within_auto_band(isolated_store):
    """STEP_MAX = AUTO_APPLY_BAND_PCT — oransal adımın tavanı hibrit kapıyı
    yapısal olarak korur: en büyük nudge bile bant-içi kalıp auto-apply olur."""
    assert trainer.STEP_MAX == store.AUTO_APPLY_BAND_PCT
    baseline = {"1h": {"sl_atr_mult": 1.2, "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}}
    proposal = {
        "generated_at": "now",
        "per_timeframe": {"1h": {"sl_atr_mult": round(1.2 * (1 + trainer.STEP_MAX), 4),
                                 "rr": 1.8, "sl_pct_floor": 0.010, "sl_pct_cap": 0.035}},
    }
    rec = store.submit_proposal(proposal, current_baseline=baseline)
    assert rec["decisions"]["1h"].startswith("auto_applied")


def test_train_flag_off_keeps_fixed_step(monkeypatch):
    """OFF yolu bayt-uyum bekçisi: nudge delta sabit 0.10, kaynak 'fixed'."""
    monkeypatch.delenv("EXIT_FORENSICS_NUDGE", raising=False)
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state",
                        lambda s: _tight_sl_rows())
    p = trainer.train(timeframes=["1h"], store_overrides={})
    sl = next(n for n in p.nudges if n.param == "sl_atr_mult")
    assert sl.delta_pct == trainer.NUDGE_STEP == 0.10
    assert sl.step_source == "fixed"
    assert sl.evidence == ""


def test_train_flag_on_uses_forensics_evidence(monkeypatch):
    """ON: trainer_evidence'tan gelen şiddet nudge adımına ve audit alanlarına yansır."""
    monkeypatch.setenv("EXIT_FORENSICS_NUDGE", "1")
    monkeypatch.setattr(trainer.paper_state, "load", lambda: object())
    monkeypatch.setattr(trainer.outcomes_mod, "outcomes_from_state",
                        lambda s: _tight_sl_rows())
    from packages.learning import exit_forensics
    monkeypatch.setattr(exit_forensics, "trainer_evidence",
                        lambda outs=None, **kw: {"1h": {"sl_roundtrip_share": 1.0}})
    p = trainer.train(timeframes=["1h"], store_overrides={})
    sl = next(n for n in p.nudges if n.param == "sl_atr_mult")
    assert sl.delta_pct == 0.15
    assert sl.step_source == "proportional(forensics)"
    assert "sl_roundtrip_share" in sl.evidence
    assert sl.new == round(sl.old * 1.15, 4)
