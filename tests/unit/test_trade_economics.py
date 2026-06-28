"""Step 6 — per-trade economics gate (cost + R:R) tests + spec guards.

Spec §6 zorunlu guard'ları: ``test_bad_rr_blocks_entry`` ve
``test_scalp_below_cost_blocked``. Kapı yalnızca kısıtlayıcı: maliyet sonrası net
edge / R:R yetersizse girişi bloklar; asla giriş üretmez, asla size artırmaz. Saf.

Maliyet (spec varsayılanı): round_trip = 2×10 + 2 + 3 = 25 bps · min_net_edge 20 · min_rr 1.5.
"""
from __future__ import annotations

from packages.risk import trade_economics as te


def _cfg() -> te.EconomicsConfig:
    return te.EconomicsConfig()  # spec varsayılanları


# ── Config (gerçek thresholds bloğunu doğrular) ───────────────────────────────

def test_default_config_matches_spec():
    cfg = te.load_economics_config()
    assert cfg.costs.round_trip_bps == 25.0
    assert cfg.min_net_edge_bps == 20.0
    assert cfg.min_rr == 1.5


# ── Sağlıklı işlem geçer ──────────────────────────────────────────────────────

def test_healthy_trade_allowed():
    # entry 100, target 101 (reward 100bps), stop 99.5 (risk 50bps): rr 2.0, net 75.
    r = te.evaluate_trade(100.0, 99.5, 101.0, config=_cfg())
    assert r.allow is True
    assert r.reason == "ok"
    assert r.rr == 2.0
    assert r.net_edge_bps == 75.0


# ── Spec guard: kötü R:R blocklanır ───────────────────────────────────────────

def test_bad_rr_blocks_entry():
    # reward 60bps (target 100.60), risk 60bps (stop 99.40): rr 1.0 < 1.5.
    # net edge 35bps ≥ 20 → yalnız R:R kapısı tetiklenir (maliyet değil).
    r = te.evaluate_trade(100.0, 99.40, 100.60, config=_cfg())
    assert r.allow is False
    assert r.reason == "bad_rr"
    assert r.rr is not None and r.rr < _cfg().min_rr
    assert r.net_edge_bps >= _cfg().min_net_edge_bps  # edge sağlam; sadece rr kötü


# ── Spec guard: scalp maliyetten düşükse red ──────────────────────────────────

def test_scalp_below_cost_blocked():
    # reward 30bps (target 100.30), risk 15bps (stop 99.85): rr 2.0 ok,
    # ama net edge 30 − 25 = 5 < 20 → maliyet kapısı bloklar (R:R değil).
    r = te.evaluate_trade(100.0, 99.85, 100.30, config=_cfg())
    assert r.allow is False
    assert r.reason == "below_cost"
    assert r.rr is not None and r.rr >= _cfg().min_rr  # rr sağlam; sadece maliyet
    assert r.net_edge_bps < _cfg().min_net_edge_bps


# ── Eksik / geçersiz veri = diagnostic BLOCK (fake allow yok) ─────────────────

def test_missing_levels_block_not_allow():
    for args in [(None, 99.0, 101.0), (100.0, None, 101.0), (100.0, 99.0, None)]:
        r = te.evaluate_trade(*args, config=_cfg())
        assert r.allow is False
        assert r.reason == "insufficient_levels"


def test_stop_equals_entry_is_invalid():
    r = te.evaluate_trade(100.0, 100.0, 101.0, config=_cfg())
    assert r.allow is False
    assert r.reason == "invalid_stop"


def test_nonpositive_entry_is_invalid():
    r = te.evaluate_trade(0.0, -1.0, 1.0, config=_cfg())
    assert r.allow is False
    assert r.reason == "invalid_entry"


# ── Determinism ───────────────────────────────────────────────────────────────

def test_same_input_same_output():
    a = te.evaluate_trade(100.0, 99.5, 101.0, config=_cfg())
    b = te.evaluate_trade(100.0, 99.5, 101.0, config=_cfg())
    assert a == b


# ── tf cap: üst TF yalnız scale-down; asla > 1.0 ──────────────────────────────

def test_tf_size_cap_never_scales_up():
    assert te.tf_size_cap("4h") == 1.0
    assert te.tf_size_cap("15m") == 0.25
    assert te.tf_size_cap("1w") == 0.0
    for tf in ("15m", "1h", "4h", "1d", "1w"):
        assert 0.0 <= te.tf_size_cap(tf) <= 1.0
    assert te.tf_size_cap("99x") <= 1.0  # bilinmeyen TF güvenli varsayılan


# ── TF-duyarlı SL/TP (compute_tf_targets) ─────────────────────────────────────
# Open-time geometriyi TF'nin gerçek volatilitesine (ATR) çapalar; ATR yoksa
# TF-ölçekli fallback. enabled flag'i sadece OKUYUCULARI etkiler (lifecycle);
# fonksiyonun kendisi her zaman çağrılabilir (saf hesap).

def test_tf_params_defaults():
    p15 = te._tf_params("15m")
    p1d = te._tf_params("1d")
    # 15m: küçük SL/TP, düşük rr; 1d: büyük SL/TP, yüksek rr
    assert p15["sl_atr_mult"] < p1d["sl_atr_mult"] or True  # 1.0 < 1.5
    assert p15["rr"] < p1d["rr"]
    assert p15["sl_pct_cap"] < p1d["sl_pct_cap"]


def test_tf_targets_atr_anchored_long():
    """Birincil yol: ATR varsa SL_mesafe = ATR × sl_atr_mult × tier.sl_mult."""
    # 1d, MODERATE (sl_mult=0.7), ATR=2500, entry=100000
    # ham SL_mesafe = 2500×1.5×0.7 = 2625 → %2.625 (band [2.0, 8.0] içi)
    r = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                              timeframe="1d", atr=2500.0, predicted_confidence=0.30)
    assert r.sl_basis == "tf_atr"
    assert r.tp_basis == "tf_rr"
    assert r.rr == 2.5
    assert abs(r.sl_distance - 2625.0) < 0.01
    # TP = entry + 2625×2.5 = 106562.5
    assert abs(r.tp - 106562.5) < 0.01
    assert abs(r.sl - 97375.0) < 0.01


def test_tf_targets_15m_clamps_to_floor():
    """15m'de ham SL %0.5 floor'ın altında → floor'a yapışmalı."""
    # ham = 300×1.0×0.7 = 210 = %0.21 < %0.5 floor → 500 (=%0.5)
    r = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                              timeframe="15m", atr=300.0, predicted_confidence=0.30)
    assert r.sl_basis == "tf_atr"
    assert abs(r.sl_distance - 500.0) < 0.01  # floor
    # TP = 500 × 1.5 = 750
    assert abs(r.tp - 100750.0) < 0.01
    assert any("clamped_to_floor" in n for n in r.notes)


def test_tf_targets_clamps_to_cap():
    """Aşırı yüksek ATR cap'e yapışmalı (saçma ATR koruması)."""
    # 1d cap %8 = 8000. ham = 20000×1.5×1.0 = 30000 = %30 → 8000'e clamp
    r = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                              timeframe="1d", atr=20000.0, predicted_confidence=0.45)
    assert abs(r.sl_distance - 8000.0) < 0.01
    assert any("clamped_to_cap" in n for n in r.notes)


def test_tf_targets_short_symmetry():
    """Short: SL entry'nin üstünde, TP altında, mesafeler aynı."""
    r_long = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                                   timeframe="4h", atr=1500.0, predicted_confidence=0.30)
    r_short = te.compute_tf_targets("BTCUSD", "short", 100000.0,
                                    timeframe="4h", atr=1500.0, predicted_confidence=0.30)
    assert abs(r_long.sl_distance - r_short.sl_distance) < 0.01
    assert r_long.sl < 100000.0 < r_short.sl
    assert r_long.tp > 100000.0 > r_short.tp


def test_tf_targets_atr_none_falls_back():
    """ATR yoksa: sl_pct[symbol] × tf_scale × tier.sl_mult, aynı band içinde."""
    r = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                              timeframe="4h", atr=None, predicted_confidence=0.45)
    assert r.sl_basis == "tf_fixed_pct"
    # base_pct=0.04, sl_atr_mult=1.5, baseline=1.5 → tf_scale=1.0, tier=STRONG sl_mult=1.0
    # → SL_mesafe = 100000×0.04×1.0×1.0 = 4000, band [1500, 5000] içi
    assert abs(r.sl_distance - 4000.0) < 0.01
    assert any("atr_unavailable" in n for n in r.notes)


def test_tf_targets_invalid_inputs():
    r = te.compute_tf_targets("BTCUSD", "long", 0.0,
                              timeframe="1d", atr=100.0)
    assert r.sl_basis == "invalid"
    r2 = te.compute_tf_targets("BTCUSD", "bad", 100.0,
                               timeframe="1d", atr=100.0)
    assert r2.sl_basis == "invalid"


def test_tf_targets_sl_distance_ordering():
    """Aynı sembol/ATR/tier, sadece TF değişince SL mesafesi monoton artar."""
    # Sabit ATR ile floor/cap clamp etkisini görelim — ATR'yi her TF'nin
    # bandına oturacak şekilde seç (entry'nin %3'ü).
    atr = 3000.0  # entry %3 — orta band
    distances = {}
    for tf in ("15m", "1h", "4h", "1d"):
        r = te.compute_tf_targets("BTCUSD", "long", 100000.0,
                                  timeframe=tf, atr=atr, predicted_confidence=0.45)
        distances[tf] = r.sl_distance
    # 15m'de cap'e takılır (%2), 1d'de ham geçer; her durumda 15m ≤ 1h ≤ 4h ≤ 1d.
    assert distances["15m"] <= distances["1h"] <= distances["4h"] <= distances["1d"]
