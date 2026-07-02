"""F4-3 — partial-TP + breakeven stop (shadow-first) testleri.

- Flag KAPALI (default): davranış bayt-aynı — kısmi kapatma YOK, SL taşınmaz;
  shadow izleri (r_hit / be_touched / hipotetik PnL) yine damgalanır.
- Flag AÇIK: tetikte close_fraction kadar PARTIAL_TP_EXIT + breakeven SL.
- SL'siz pozisyon: R tanımsız → hiçbir şey (uydurma risk mesafesi yok).
- summary(): shadow-vs-actual doğru toplanır.
"""
from __future__ import annotations

import importlib

import pytest

from packages.data.registry.loader import threshold_override

_ON = {"partial_tp": {"enabled": True, "trigger_r": 1.0, "close_fraction": 0.5, "breakeven": True}}
_ON_NO_BE = {"partial_tp": {"enabled": True, "trigger_r": 1.0, "close_fraction": 0.5, "breakeven": False}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(tmp_path / "paper_audit.jsonl"))
    monkeypatch.setenv("DECISION_LOG_PATH", str(tmp_path / "decision_log.jsonl"))
    from packages.paper import state as ps
    importlib.reload(ps)
    from packages.paper import lifecycle as lc
    importlib.reload(lc)
    return ps, lc


def _open_long(ps, lc, entry=100.0, sl=96.0, size=1000.0):
    state = ps.load()
    pos = lc.open_position(
        state, symbol="BTCUSD", side="long", entry_price=entry,
        size_multiplier=0.0, manual=True, size_usd_override=size,
    )
    pos.sl, pos.tp = sl, 200.0  # test geometrisi: R=4, TP uzakta
    pos.valid_until = None      # time-stop devre dışı (test izolasyonu)
    pos.trail_distance_pct = None  # trailing devre dışı — yalnız ptp yolu test edilir
    return state, pos


# ------------------------------ flag KAPALI -----------------------------------

def test_flag_off_observes_but_does_not_act(env) -> None:
    ps, lc = env
    state, pos = _open_long(ps, lc)
    # 1R = 104: r-hit damgalanır ama pozisyon PARÇALANMAZ, SL taşınmaz
    assert lc.tick(state, {"BTCUSD": 104.0}) == []
    assert pos.ptp_r_hit_at is not None and pos.ptp_price_at_r == 104.0
    assert pos.size_usd == 1000.0 and pos.sl == 96.0
    # girişe dönüş → breakeven senaryosu işaretlenir (yine aksiyon yok)
    assert lc.tick(state, {"BTCUSD": 100.0}) == []
    assert pos.ptp_be_touched is True
    # SL'e düşüş → tam kapanış; Trade shadow izlerini taşır
    closed = lc.tick(state, {"BTCUSD": 96.0})
    assert len(closed) == 1
    t = closed[0]
    assert t.close_reason == "SL_HIT" and t.pnl_usd == pytest.approx(-40.0)
    assert t.ptp_r_hit is True
    # hipotetik: %50'si 104'te (+20) + kalan %50 breakeven (0) = +20
    assert t.ptp_shadow_pnl_usd == pytest.approx(20.0)


def test_flag_off_no_r_hit_leaves_no_shadow(env) -> None:
    ps, lc = env
    state, _pos = _open_long(ps, lc)
    lc.tick(state, {"BTCUSD": 101.0})   # 1R'ye değmedi
    closed = lc.tick(state, {"BTCUSD": 96.0})
    assert closed[0].ptp_r_hit is False
    assert closed[0].ptp_shadow_pnl_usd is None


def test_no_sl_means_no_r_no_action(env) -> None:
    ps, lc = env
    state, pos = _open_long(ps, lc)
    pos.sl = None
    with threshold_override(_ON):
        assert lc.tick(state, {"BTCUSD": 150.0}) == []
    assert pos.ptp_r_hit_at is None and pos.size_usd == 1000.0


# ------------------------------- flag AÇIK ------------------------------------

def test_flag_on_partial_close_and_breakeven(env) -> None:
    ps, lc = env
    state, pos = _open_long(ps, lc)
    with threshold_override(_ON):
        closed = lc.tick(state, {"BTCUSD": 104.0})
        # %50 kısmi kapanış: +%4 × 500$ = +20$; kalan 500$, SL girişe çekildi
        assert len(closed) == 1
        leg = closed[0]
        assert leg.close_reason == "PARTIAL_TP_EXIT"
        assert leg.pnl_usd == pytest.approx(20.0)
        assert leg.id != pos.id                      # F1-5 benzersiz leg id
        assert pos.size_usd == pytest.approx(500.0)
        assert pos.sl == pytest.approx(100.0)        # breakeven
        assert pos.ptp_done is True
        # ikinci tetik YOK (bir kez)
        assert lc.tick(state, {"BTCUSD": 105.0}) == []
        # girişe dönüş → kalan yarı breakeven SL'den kapanır (0$)
        rest = lc.tick(state, {"BTCUSD": 100.0})
        assert len(rest) == 1 and rest[0].close_reason == "SL_HIT"
        assert rest[0].pnl_usd == pytest.approx(0.0)
        # gerçek ptp uygulandı → shadow alanı None (gerçek leg'ler ölçüm)
        assert rest[0].ptp_shadow_pnl_usd is None
    # net: eski davranışta −40 olacak senaryo +20'ye döndü
    assert state.realized_pnl_usd == pytest.approx(20.0)


def test_flag_on_short_side_and_no_breakeven(env) -> None:
    ps, lc = env
    state = ps.load()
    pos = lc.open_position(
        state, symbol="BTCUSD", side="short", entry_price=100.0,
        size_multiplier=0.0, manual=True, size_usd_override=1000.0,
    )
    pos.sl, pos.tp, pos.valid_until = 104.0, 50.0, None  # R=4 (short)
    pos.trail_distance_pct = None
    with threshold_override(_ON_NO_BE):
        closed = lc.tick(state, {"BTCUSD": 96.0})  # short 1R kârda
        assert closed[0].close_reason == "PARTIAL_TP_EXIT"
        assert closed[0].pnl_usd == pytest.approx(20.0)
        assert pos.sl == 104.0  # breakeven kapalı → SL DOKUNULMADI


def test_full_exit_takes_priority_over_partial(env) -> None:
    """Gap ile doğrudan TP'ye giden pozisyon parçalanmaz — tam TP kapanışı."""
    ps, lc = env
    state, pos = _open_long(ps, lc)
    pos.tp = 108.0
    with threshold_override(_ON):
        closed = lc.tick(state, {"BTCUSD": 110.0})
    assert len(closed) == 1 and closed[0].close_reason == "TP_HIT"
    assert pos not in state.open_positions


# -------------------------------- summary -------------------------------------

def test_shadow_summary_aggregates(env) -> None:
    ps, lc = env
    from packages.learning import partial_tp_shadow
    state, _pos = _open_long(ps, lc)
    lc.tick(state, {"BTCUSD": 104.0})
    lc.tick(state, {"BTCUSD": 100.0})
    lc.tick(state, {"BTCUSD": 96.0})   # actual −40, shadow +20
    s = partial_tp_shadow.summary(state)
    assert s["enabled"] is False
    assert s["r_hit_trades"] == 1 and s["evaluable_trades"] == 1
    assert s["actual_pnl_usd"] == pytest.approx(-40.0)
    assert s["shadow_pnl_usd"] == pytest.approx(20.0)
    assert s["uplift_usd"] == pytest.approx(60.0)
