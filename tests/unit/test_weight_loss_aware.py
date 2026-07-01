"""CP4-fix #3 — kayıp-farkında ağırlık skoru (WEIGHT_LOSS_AWARE)."""
from __future__ import annotations

from packages.learning import auto_weight_trainer as t
from packages.learning.outcomes import CanonicalOutcome


def _o(pnl, module="touche"):
    return CanonicalOutcome(
        trade_id="t", symbol="X", timeframe="1d", opened_at=None, closed_at=None,
        duration_seconds=None, direction="long", open_price=1.0, close_price=1.0,
        pnl=pnl, pnl_pct=None, open_reason=None, close_reason=None,
        fingerprint=f"X|v2|1d|NEUTRAL|long|S55|X|{module}",
        regime="NEUTRAL", dominant_module=module, candidate_action=None,
        final_action=None, data_verified=True,
    )


def test_loss_aware_penalizes_big_losses():
    # Aynı win_rate (%60) ama biri küçük kayıp, diğeri DEV kayıp → dev kayıp düşük skor.
    small_loss = [10.0, 10.0, 10.0, -10.0, -10.0]      # net +10
    big_loss = [10.0, 10.0, 10.0, -100.0, -100.0]      # net -170, aynı win_rate
    wr = 0.6
    assert t._loss_aware_score(wr, big_loss) < t._loss_aware_score(wr, small_loss)


def test_loss_aware_net_loser_scores_below_winrate_base():
    # Net kaybeden modül, saf win_rate*100'ün ALTINA iner (ceza gerçek).
    pnls = [5.0, 5.0, -50.0, -50.0]  # win %50 ama net -90
    assert t._loss_aware_score(0.5, pnls) < 50.0


def test_winsorize_resists_single_outlier():
    # Tek dev kazanç skoru şişirmemeli (winsorize n>=20'de kuyruğu kırpar).
    common = [3.0] * 15 + [-5.0] * 9  # 24 işlem taban
    with_outlier = [*common, 2000.0]   # tek dev kazanç
    with_normal = [*common, 5.0]       # aynı ama outlier normal değerde
    # winsorize dev kazancı kırpar → iki skor birbirine yakın
    assert abs(
        t._loss_aware_score(0.6, with_outlier) - t._loss_aware_score(0.6, with_normal)
    ) < 5.0


def test_flag_off_uses_old_score(monkeypatch):
    monkeypatch.delenv("WEIGHT_LOSS_AWARE", raising=False)
    outs = [_o(10.0)] * 3 + [_o(-100.0)] * 3  # touche net -270
    perfs, _ = t._aggregate(outs)
    tou = next(p for p in perfs if p.module == "touche")
    # Eski skor: win_rate*100 + clamp(avg/1000) → avg=-45 → term ~-0.045 → ~50
    old = t._module_score(tou.win_rate, tou.avg_pnl)
    assert abs(tou.score - old) < 0.01


def test_flag_on_uses_loss_aware(monkeypatch):
    monkeypatch.setenv("WEIGHT_LOSS_AWARE", "1")
    outs = [_o(10.0)] * 3 + [_o(-100.0)] * 3
    perfs, _ = t._aggregate(outs)
    tou = next(p for p in perfs if p.module == "touche")
    # Kayıp-farkında skor eski skordan belirgin düşük (net kaybeden cezalı)
    assert tou.score < t._module_score(tou.win_rate, tou.avg_pnl)
