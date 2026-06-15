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
