"""Konviksiyon-kademeli risk + trailing stop testleri."""
from __future__ import annotations

from packages.paper import conviction
from packages.paper import lifecycle as L
from packages.paper import state as S


def test_tier_for_maps_confidence_to_tier():
    assert conviction.tier_for(0.22).name == "WEAK"
    assert conviction.tier_for(0.35).name == "MODERATE"
    assert conviction.tier_for(0.50).name == "STRONG"
    # None → nötr (çarpan yok)
    assert conviction.tier_for(None).size_mult == 1.0


def test_weak_tier_smaller_size_and_closer_stop_than_strong():
    ps = S._initial_state()
    weak = L.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, predicted_confidence=0.22, timeframe="1h",
    )
    strong = L.open_position(
        ps, symbol="ETHUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, predicted_confidence=0.50, timeframe="1h",
    )
    assert weak.tier == "WEAK" and strong.tier == "STRONG"
    assert weak.size_usd < strong.size_usd          # zayıf = küçük boyut
    assert weak.sl > strong.sl                       # zayıf long = daha YAKIN stop
    assert weak.trail_distance_pct < strong.trail_distance_pct


def test_trailing_stop_locks_profit_and_exits_on_pullback():
    ps = S._initial_state()
    pos = L.open_position(
        ps, symbol="BTCUSD", side="long", entry_price=100.0,
        size_multiplier=1.0, predicted_confidence=0.22, timeframe="1h",
    )  # WEAK: trail_distance 0.008, activate 0.01
    # Lehe %2 → trailing aktif, tepe 102 kilitlenir; SL/TP'ye değmedi.
    L.tick(ps, {"BTCUSD": 102.0})
    assert pos.trail_active is True and pos.trail_peak == 102.0
    assert any(p.id == pos.id for p in ps.open_positions)  # hâlâ açık
    # Tepeden %0.8'den fazla geri çekilme → trailing exit.
    closed = L.tick(ps, {"BTCUSD": 101.0})
    assert [t.close_reason for t in closed] == ["TRAILING_STOP_EXIT"]
    assert not any(p.id == pos.id for p in ps.open_positions)  # kapandı
