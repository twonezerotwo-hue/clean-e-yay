"""Y-2 — üçlü-bariyer etiketi testleri.

barrier_label = exit_forensics teşhisinin (_category/_diagnose) İNCE sarmalayıcısı;
eşikler (roundtrip 0.5R, never_worked MIN_MOVE, capture 0.5) oradan gelir — bu
testler ETİKET eşlemesini kilitler (şanslı/hakiki ayrımı Y-5'in eğitim etiketi).
"""
from __future__ import annotations

from packages.learning import dataset_health, exit_forensics
from packages.learning.outcomes import CanonicalOutcome


def _o(close_reason, pnl_pct, *, mae=0.0, mfe=0.0, risk_pct=None):
    return CanonicalOutcome(
        trade_id="t", symbol="BTCUSD", timeframe="4h", opened_at=None,
        closed_at=None, duration_seconds=None, direction="long",
        open_price=100.0, close_price=None, pnl=0.0, pnl_pct=pnl_pct,
        open_reason="auto", close_reason=close_reason, fingerprint="fp",
        regime="NEUTRAL", dominant_module="touche", candidate_action=None,
        final_action=None, data_verified=True, mae_pct=mae, mfe_pct=mfe,
        risk_pct=risk_pct,
    )


def test_tp_is_clean_win():
    lbl = exit_forensics.barrier_label(_o("TP_HIT", 2.0, mfe=2.5))
    assert lbl == {"barrier": "TP", "quality": "clean_win"}


def test_trailing_low_capture_is_partial():
    # mfe %4, pnl %1 → capture 0.25 < 0.5 → kısmi yakalama (giveback kanıtı).
    lbl = exit_forensics.barrier_label(_o("TRAILING_STOP_EXIT", 1.0, mfe=4.0))
    assert lbl == {"barrier": "TRAIL", "quality": "partial_capture"}


def test_trailing_high_capture_is_clean():
    lbl = exit_forensics.barrier_label(_o("TRAILING_STOP_EXIT", 3.0, mfe=4.0))
    assert lbl == {"barrier": "TRAIL", "quality": "clean_win"}


def test_sl_roundtrip_vs_straight():
    # risk %2, mfe %1.5 → mfe_r 0.75 ≥ 0.5R → roundtrip (kâr korunamadı).
    rt = exit_forensics.barrier_label(_o("SL_HIT", -2.0, mfe=1.5, risk_pct=0.02))
    assert rt == {"barrier": "SL", "quality": "roundtrip_loss"}
    # mfe ~0 → hiç işlemedi → temiz kayıp (giriş sorunu, çıkış maliyeti değil).
    st = exit_forensics.barrier_label(_o("SL_HIT", -2.0, mfe=0.01, risk_pct=0.02))
    assert st == {"barrier": "SL", "quality": "clean_loss"}


def test_time_stop_lucky_vs_never_worked():
    lucky = exit_forensics.barrier_label(_o("TIME_STOP_EXPIRED", 0.4, mfe=0.8))
    assert lucky == {"barrier": "TIME", "quality": "lucky_win"}  # şanslı artı
    nw = exit_forensics.barrier_label(_o("TIME_STOP_EXPIRED", -0.1, mfe=0.01))
    assert nw == {"barrier": "TIME", "quality": "never_worked"}


def test_manual_excluded():
    lbl = exit_forensics.barrier_label(_o("MANUAL_CLOSE", 1.0))
    assert lbl == {"barrier": "MANUAL", "quality": "excluded"}


def test_dataset_health_distribution_additive():
    outs = [
        _o("TP_HIT", 2.0, mfe=2.5),
        _o("SL_HIT", -2.0, mfe=1.5, risk_pct=0.02),
        _o("TIME_STOP_EXPIRED", 0.4, mfe=0.8),
    ]
    rep = dataset_health.report(outs)
    bl = rep["barrier_labels"]
    assert bl["by_barrier"] == {"SL": 1, "TIME": 1, "TP": 1}
    assert bl["by_quality"] == {"clean_win": 1, "lucky_win": 1, "roundtrip_loss": 1}
    # Mevcut alanlar dokunulmadı (additive sözleşme).
    assert {"total", "verified", "coverage", "learners"} <= set(rep)
