"""MOVE stres bacağı tezgâh ölçümü (FAZ-2 sentinel kripto-dışı stres adayı).

MOVE bir RİSK sinyali (yön değil): doğru test "stres → ileri oynaklık" olmalı.
Tezgâh kanıtı (5y): stress_vs_fwdvol +0.11 (POZİTİF → risk-gate değerli);
return-separation karışık (yanlış enstrüman). Canlı sentinel'e HENÜZ bağlı DEĞİL.
"""
from __future__ import annotations

from packages.learning import macro_backtest as mb


def test_move_calm_direction():
    # Yüksek MOVE (stres) → düşük sakinlik; düşük MOVE → yüksek sakinlik.
    assert mb._move_calm(60.0) > mb._move_calm(150.0)
    assert 0.0 <= mb._move_calm(200.0) <= 100.0
    assert mb._move_calm(101.0) == 100.0 - 0.0  # merkez ~medyan


def test_move_calm_clamped():
    assert mb._move_calm(500.0) == 0.0     # aşırı stres → taban
    assert mb._move_calm(10.0) == 100.0    # aşırı sakin → tavan


def test_move_stress_edge_shape_and_instrument():
    rows = (
        [{"move_calm": 30.0, "fwd_vol": 5.0, "fwd_risk": -2.0,
          "fwd": {"BTC": -2.0, "GLD": 1.0, "SPY": -1.0}, "date": "2024-01-01"}] * 30
        + [{"move_calm": 80.0, "fwd_vol": 1.0, "fwd_risk": 2.0,
            "fwd": {"BTC": 2.0, "GLD": -1.0, "SPY": 1.0}, "date": "2024-01-02"}] * 30
    )
    e = mb._move_stress_edge(rows)
    # Düşük sakinlik (yüksek stres) → yüksek fwd_vol → stres↔vol POZİTİF korelasyon
    assert e["stress_vs_fwdvol_corr"] is not None and e["stress_vs_fwdvol_corr"] > 0
    assert e["stress_vs_fwdvol_n"] == 60
    assert set(e["return_terciles"]) == {"BTC", "GLD", "SPY"}


def test_move_in_backfill_registry():
    from packages.learning import macro_backfill
    assert macro_backfill.BACKFILL_TICKERS.get("MOVE") == "^MOVE"
