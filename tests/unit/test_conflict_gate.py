"""Faz 8 — conflict_gate.py guard testleri (INERT by default).

enabled=false (varsayılan) olduğu sürece evaluate() her zaman "open", 1.0
döner — eski sistemin açılış davranışı değişmez. Aktif olduğunda her
trade_profile için kademeli sıkılık (OFF/SOFT/SOFT_PLUS/HARD/HARD_MANUAL)
uygulanır.
"""
from __future__ import annotations

from packages.decision import conflict_gate, conflict_resolver

_ON = conflict_gate.ConflictGateConfig(enabled=True)
_OFF = conflict_gate.ConflictGateConfig(enabled=False)


def test_disabled_by_default_is_inert():
    r = conflict_gate.evaluate(
        trade_profile="POSITION", conflict_final_action=conflict_resolver.BLOCKED, cfg=_OFF
    )
    assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_none_trade_profile_is_inert_even_when_enabled():
    r = conflict_gate.evaluate(trade_profile=None, conflict_final_action=conflict_resolver.BLOCKED, cfg=_ON)
    assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_unknown_profile_fails_open():
    cfg = conflict_gate.ConflictGateConfig(enabled=True, profile_modes={})
    r = conflict_gate.evaluate(trade_profile="MYSTERY", conflict_final_action=conflict_resolver.BLOCKED, cfg=cfg)
    assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_scalp_is_off_regardless_of_verdict():
    for verdict in (conflict_resolver.BLOCKED, conflict_resolver.NO_TRADE, conflict_resolver.WATCH, conflict_resolver.CANDIDATE_OPEN):
        r = conflict_gate.evaluate(trade_profile="SCALP", conflict_final_action=verdict, cfg=_ON)
        assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_intraday_soft_reduces_on_no_trade_and_blocked():
    for verdict in (conflict_resolver.NO_TRADE, conflict_resolver.BLOCKED):
        r = conflict_gate.evaluate(trade_profile="INTRADAY", conflict_final_action=verdict, cfg=_ON)
        assert (r.route, r.effective_multiplier) == ("open", 0.5)


def test_intraday_soft_normal_on_watch_and_candidate():
    for verdict in (conflict_resolver.WATCH, conflict_resolver.CANDIDATE_OPEN):
        r = conflict_gate.evaluate(trade_profile="INTRADAY", conflict_final_action=verdict, cfg=_ON)
        assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_tactical_soft_plus_blocks_on_blocked():
    r = conflict_gate.evaluate(trade_profile="TACTICAL", conflict_final_action=conflict_resolver.BLOCKED, cfg=_ON)
    assert r.route == "block"


def test_tactical_soft_plus_reduces_on_no_trade():
    r = conflict_gate.evaluate(trade_profile="TACTICAL", conflict_final_action=conflict_resolver.NO_TRADE, cfg=_ON)
    assert (r.route, r.effective_multiplier) == ("open", 0.5)


def test_tactical_soft_plus_normal_on_watch_and_candidate():
    for verdict in (conflict_resolver.WATCH, conflict_resolver.CANDIDATE_OPEN):
        r = conflict_gate.evaluate(trade_profile="TACTICAL", conflict_final_action=verdict, cfg=_ON)
        assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_swing_hard_only_opens_on_candidate_open():
    r = conflict_gate.evaluate(trade_profile="SWING", conflict_final_action=conflict_resolver.CANDIDATE_OPEN, cfg=_ON)
    assert (r.route, r.effective_multiplier) == ("open", 1.0)


def test_swing_hard_blocks_on_anything_else():
    for verdict in (conflict_resolver.BLOCKED, conflict_resolver.NO_TRADE, conflict_resolver.WATCH):
        r = conflict_gate.evaluate(trade_profile="SWING", conflict_final_action=verdict, cfg=_ON)
        assert r.route == "block"


def test_position_hard_manual_queues_on_candidate_open():
    r = conflict_gate.evaluate(trade_profile="POSITION", conflict_final_action=conflict_resolver.CANDIDATE_OPEN, cfg=_ON)
    assert (r.route, r.effective_multiplier) == ("manual_ready", 1.0)


def test_position_hard_manual_blocks_on_anything_else():
    for verdict in (conflict_resolver.BLOCKED, conflict_resolver.NO_TRADE, conflict_resolver.WATCH):
        r = conflict_gate.evaluate(trade_profile="POSITION", conflict_final_action=verdict, cfg=_ON)
        assert r.route == "block"


def test_missing_verdict_treated_as_no_trade():
    r = conflict_gate.evaluate(trade_profile="INTRADAY", conflict_final_action=None, cfg=_ON)
    assert (r.route, r.effective_multiplier) == ("open", 0.5)


def test_default_profile_modes_constant_is_the_full_graduated_ladder():
    # Modülün kod-içi varsayılanı (config'te profile_modes hiç verilmezse düşülen
    # taban) — şu anki ŞİPLENMİŞ config'ten bağımsız, kademeli tasarımın referansı.
    assert conflict_gate._DEFAULT_PROFILE_MODES == {
        "SCALP": "OFF",
        "INTRADAY": "SOFT",
        "TACTICAL": "SOFT_PLUS",
        "SWING": "HARD",
        "POSITION": "HARD_MANUAL",
    }


def test_load_config_reflects_shipped_position_pilot():
    # 2026-06-26: POSITION pilotu aktif (owner onayı, ARCHITECTURE.md §7.5) —
    # diğer profiller veri birikene kadar kasıtlı OFF. Bu test config/thresholds
    # değiştiğinde bilinçli güncellenmeli; sürpriz drift'i yakalar.
    cfg = conflict_gate.load_config()
    assert cfg.enabled is True
    assert cfg.profile_modes == {
        "SCALP": "OFF",
        "INTRADAY": "OFF",
        "TACTICAL": "OFF",
        "SWING": "OFF",
        "POSITION": "HARD_MANUAL",
    }
