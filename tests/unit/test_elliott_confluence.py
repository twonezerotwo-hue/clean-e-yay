"""T-2 — Elliott × Fib confluence (`technical.elliott_confluence`) testleri.

- `extra_levels` verilmezse `_confluence_zones` BİREBİR eski davranış (bayt-aynı).
- Elliott seviyesi mevcut S/R bandına düşerse bölgeye `elliott_*` bileşeni girer.
- Fib + Elliott aynı bölgedeyse konum kanadı 0.6→0.8 tartar (yalnız flag AÇIK);
  tavan 0.9 (sr_strength ile birlikte bile aşılmaz).
- Elliott asla tek başına bölge/skor üretemez (2 fiyat şartı aynen geçerli).
"""
from __future__ import annotations

from packages.data.providers.technical import timeframe as tf
from packages.data.types import TechnicalConfluenceZone


def _zones(extra=None):
    # current=100; swing support 99.5 + fib desteği 99.8 aynı bantta (tol %2'ye clamp).
    return tf._confluence_zones(
        100.0, 3.0, 99.5, None, None,
        _fib_near(99.8, "support"),
        extra_levels=extra,
    )


def _fib_near(price: float, role: str):
    from packages.data.types import FibonacciAnalysis, FibonacciLevel
    return FibonacciAnalysis(
        timeframe="1D",
        zone="near_support" if role == "support" else "near_resistance",
        validity="sane",
        nearest_level=FibonacciLevel(
            ratio=0.618, label="0.618", price=price, kind="retracement", role=role
        ),
    )


def test_no_extra_levels_is_byte_identical_baseline():
    base = _zones(extra=None)
    assert len(base) == 1
    assert base[0].components == ["swing_support", "fib_0.618"]


def test_elliott_level_joins_matching_band():
    zones = _zones(extra=[("elliott_invalidation", 99.6)])
    assert len(zones) == 1
    assert "elliott_invalidation" in zones[0].components
    assert zones[0].kind == "support"


def test_elliott_level_far_away_does_not_join():
    # Banda (tol) sığmayan seviye bölgeyi bozar/katılamaz — tüm fiyatlar tolerans
    # içinde olmalı; uzak elliott seviyesi eklenirse bölge OLUŞMAZ (dürüst davranış:
    # uyumsuz kanıt bölgeyi şişirmez).
    zones = _zones(extra=[("elliott_invalidation", 90.0)])
    assert zones == []


def test_elliott_alone_cannot_form_zone():
    # Tek fiyat (yalnız elliott) → bölge yok (≥2 bağımsız fiyat şartı).
    zones = tf._confluence_zones(100.0, 3.0, None, None, None, None,
                                 extra_levels=[("elliott_target", 99.5)])
    assert zones == []


def _zone(comps, kind="support", price=99.5):
    return TechnicalConfluenceZone(price=price, kind=kind, components=comps)


def test_side_weight_flags_off_is_fixed_06():
    z = [_zone(["swing_support", "fib_0.618", "elliott_invalidation"])]
    assert tf._zone_side_weight("support", z) == 0.6


def test_side_weight_elliott_plus_fib_boosts_to_08():
    z = [_zone(["swing_support", "fib_0.618", "elliott_invalidation"])]
    assert tf._zone_side_weight("support", z, elliott_boost_on=True) == 0.8


def test_side_weight_elliott_without_fib_no_boost():
    # Elliott var ama fib yok — "iki bağımsız yöntem aynı seviyede" şartı yok.
    z = [_zone(["swing_support", "elliott_invalidation"])]
    assert tf._zone_side_weight("support", z, elliott_boost_on=True) == 0.6


def test_side_weight_cap_09_with_sr_strength():
    z = [_zone(["swing_support", "fib_0.618", "elliott_invalidation"])]
    w = tf._zone_side_weight(
        "support", z, sr_touches={"support": 4}, sr_strength_on=True, elliott_boost_on=True
    )
    assert w == 0.9  # 0.6 + 0.1 (3+ dokunuş) + 0.2 (fib+elliott) = 0.9 tavan


def test_direction_score_flag_off_ignores_elliott_component():
    # Bölge elliott bileşeni taşısa bile flag KAPALIYKEN ağırlık 0.6 sabit —
    # skor, elliott'suz bölgeyle birebir aynı.
    cfg_off = tf.TechnicalConfig()
    z_ell = [_zone(["swing_support", "fib_0.618", "elliott_invalidation"])]
    z_plain = [_zone(["swing_support", "fib_0.618"])]
    s_ell, _ = tf._direction_score(70.0, 0.0, "bullish", zones=z_ell, cfg=cfg_off)
    s_plain, _ = tf._direction_score(70.0, 0.0, "bullish", zones=z_plain, cfg=cfg_off)
    assert s_ell == s_plain


def test_direction_score_flag_on_confirms_stronger():
    cfg_on = tf.TechnicalConfig(elliott_confluence_enabled=True)
    cfg_off = tf.TechnicalConfig()
    z = [_zone(["swing_support", "fib_0.618", "elliott_invalidation"])]
    s_on, _ = tf._direction_score(70.0, 0.0, "bullish", zones=z, cfg=cfg_on)
    s_off, _ = tf._direction_score(70.0, 0.0, "bullish", zones=z, cfg=cfg_off)
    assert s_on > s_off  # 0.8'lik destek teyidi 0.6'dan güçlü
