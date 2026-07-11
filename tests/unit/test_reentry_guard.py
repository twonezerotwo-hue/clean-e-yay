"""Tekrar-giriş kilidi (reentry_guard) — kapanış sonrası bayat-sinyal geri-girişi.

Owner kararı (2026-07-11): kilit KURAN = MANUAL veya kârlı-otomatik; AÇILIR ancak
İKİSİ birden (taze bar + sinyal değişti). Ters yön hiç kilitlenmez. Flag default
KAPALI (shadow: locked hesaplanır, active=False).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.paper import reentry_guard
from packages.paper.state import PaperState, Trade

_FP_A = "BTCUSD|v2|4h|OFFENSIVE|long|S65|C|sentinel"
_FP_B = "BTCUSD|v2|4h|OFFENSIVE|long|S80|C|momentum"  # farklı bucket+module


def _trade(**kw) -> Trade:
    base = dict(
        id="t1", symbol="BTCUSD", side="long", entry_price=100.0, exit_price=110.0,
        pnl_usd=10.0, opened_at="2026-07-11T00:00:00+00:00",
        closed_at="2026-07-11T04:00:00+00:00", close_reason="TP_HIT",
        timeframe="4h", lifecycle_status="CLOSED", fingerprint=_FP_A,
    )
    base.update(kw)
    return Trade(**base)


def _state(trades: list[Trade]) -> PaperState:
    return PaperState(equity_usd=10000.0, peak_equity_usd=10000.0, recent_trades=list(trades))


def _now(closed_at: str, *, plus_sec: float) -> datetime:
    return datetime.fromisoformat(closed_at) + timedelta(seconds=plus_sec)


def _assess(state, *, fingerprint=_FP_A, now, enabled=False):
    return reentry_guard.assess(
        state, symbol="BTCUSD", side="long", timeframe="4h",
        fingerprint=fingerprint, now=now, cfg={"enabled": enabled},
    )


# ── kilit KURAN kapanışlar ───────────────────────────────────────────────────

def test_no_lock_when_no_matching_close():
    r = _assess(_state([]), now=datetime.now(UTC))
    assert r == {}


def test_profitable_auto_close_arms_lock():
    t = _trade(close_reason="TP_HIT", pnl_usd=25.0, lifecycle_status="CLOSED")
    # taze bar geçmedi (1 saat < 4h) → kilitli
    r = _assess(_state([t]), now=_now(t.closed_at, plus_sec=3600))
    assert r["locked"] is True and r["armed_by"] == "TP_HIT"


def test_manual_close_arms_lock_even_with_zero_pnl():
    # owner manuel kapanış (FORCE_CLOSED + pnl 0) yine kilit kurar
    t = _trade(close_reason="MANUAL", pnl_usd=0.0, lifecycle_status="FORCE_CLOSED")
    r = _assess(_state([t]), now=_now(t.closed_at, plus_sec=60))
    assert r["locked"] is True and r["armed_by"] == "MANUAL"


def test_losing_auto_close_does_not_arm():
    t = _trade(close_reason="SL_HIT", pnl_usd=-30.0, lifecycle_status="CLOSED")
    assert _assess(_state([t]), now=_now(t.closed_at, plus_sec=60)) == {}


def test_force_close_risk_exit_does_not_arm_even_if_profitable():
    t = _trade(close_reason="KILL_SWITCH_EXIT", pnl_usd=40.0, lifecycle_status="FORCE_CLOSED")
    assert _assess(_state([t]), now=_now(t.closed_at, plus_sec=60)) == {}


# ── kilit AÇILMA: İKİSİ birden ───────────────────────────────────────────────

def test_locked_when_fresh_bar_but_same_signal():
    t = _trade(fingerprint=_FP_A)
    r = _assess(_state([t]), fingerprint=_FP_A, now=_now(t.closed_at, plus_sec=5 * 3600))
    assert r["fresh_bar"] is True and r["signal_changed"] is False
    assert r["locked"] is True and "sinyal_ayni" in r["reason"]


def test_locked_when_signal_changed_but_no_fresh_bar():
    t = _trade(fingerprint=_FP_A)
    r = _assess(_state([t]), fingerprint=_FP_B, now=_now(t.closed_at, plus_sec=600))
    assert r["fresh_bar"] is False and r["signal_changed"] is True
    assert r["locked"] is True and "taze_bar_bekleniyor" in r["reason"]


def test_released_when_fresh_bar_and_signal_changed():
    t = _trade(fingerprint=_FP_A)
    r = _assess(_state([t]), fingerprint=_FP_B, now=_now(t.closed_at, plus_sec=5 * 3600))
    assert r["fresh_bar"] is True and r["signal_changed"] is True
    assert r["locked"] is False and r["reason"] is None


# ── ters yön hiç kilitlenmez ─────────────────────────────────────────────────

def test_opposite_side_not_locked():
    t = _trade(side="long")
    r = reentry_guard.assess(
        _state([t]), symbol="BTCUSD", side="short", timeframe="4h",
        fingerprint=_FP_A, now=_now(t.closed_at, plus_sec=60), cfg={"enabled": True},
    )
    assert r == {}


# ── en son kapanış güncel durumu belirler ────────────────────────────────────

def test_latest_close_wins_losing_stop_clears_prior_lock():
    win = _trade(id="w", close_reason="TP_HIT", pnl_usd=20.0,
                 closed_at="2026-07-11T04:00:00+00:00")
    later_loss = _trade(id="l", close_reason="SL_HIT", pnl_usd=-15.0,
                        lifecycle_status="CLOSED", closed_at="2026-07-11T08:00:00+00:00")
    # en son kapanış zararlı stop → kilit yok
    r = _assess(_state([win, later_loss]), now=_now(later_loss.closed_at, plus_sec=60))
    assert r == {}


# ── legacy fingerprint eksikse taze-bar kapısı kalır ─────────────────────────

def test_missing_fingerprint_falls_back_to_fresh_bar_only():
    t = _trade(fingerprint=None)
    # fingerprint yok → signal_changed True (kalıcı kilit uydurma); taze bar geçmedi → kilitli
    r = _assess(_state([t]), fingerprint=None, now=_now(t.closed_at, plus_sec=600))
    assert r["signal_changed"] is True and r["fresh_bar"] is False and r["locked"] is True
    # taze bar geçince açılır
    r2 = _assess(_state([t]), fingerprint=None, now=_now(t.closed_at, plus_sec=5 * 3600))
    assert r2["locked"] is False


# ── shadow: flag KAPALIYKEN active False ─────────────────────────────────────

def test_active_reflects_flag():
    t = _trade()
    now = _now(t.closed_at, plus_sec=600)
    assert _assess(_state([t]), now=now, enabled=False)["active"] is False
    assert _assess(_state([t]), now=now, enabled=True)["active"] is True


# ── attempt_open kablolaması (uçtan uca) ─────────────────────────────────────

def _recent_win() -> Trade:
    """1 saat önce kârda TP kapanmış aynı-yön işlem (taze bar geçmedi → kilitli)."""
    closed = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    return _trade(close_reason="TP_HIT", pnl_usd=20.0, lifecycle_status="CLOSED",
                  closed_at=closed, fingerprint=_FP_A)


def _lc_with_flag(monkeypatch, *, enabled: bool):
    import packages.paper.lifecycle as lc
    real = lc.load_thresholds
    def patched():
        d = dict(real())
        d["reentry_guard"] = {"enabled": enabled}
        return d
    monkeypatch.setattr(lc, "load_thresholds", patched)
    return lc


def test_attempt_open_blocks_when_enabled_and_locked(monkeypatch):
    lc = _lc_with_flag(monkeypatch, enabled=True)
    ps = _state([_recent_win()])
    pos, decision = lc.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0, size_multiplier=1.0,
        timeframe="4h", fingerprint=_FP_A, apply_reentry_guard=True,
    )
    assert pos is None and decision["allowed"] is False
    assert decision["reason"].startswith("reentry_locked")
    assert ps.open_positions == []


def test_attempt_open_opens_when_flag_disabled_shadow(monkeypatch):
    lc = _lc_with_flag(monkeypatch, enabled=False)
    ps = _state([_recent_win()])
    pos, decision = lc.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0, size_multiplier=1.0,
        timeframe="4h", fingerprint=_FP_A, apply_reentry_guard=True,
    )
    # shadow: rapor decision'a taşınır ama açılış engellenmez
    assert pos is not None and decision["allowed"] is True
    assert decision["reentry_guard"]["locked"] is True
    assert decision["reentry_guard"]["active"] is False


def test_attempt_open_owner_path_not_guarded(monkeypatch):
    # apply_reentry_guard default False (owner manuel/manual_ready) → flag açık olsa da açar
    lc = _lc_with_flag(monkeypatch, enabled=True)
    ps = _state([_recent_win()])
    pos, decision = lc.attempt_open(
        ps, symbol="BTCUSD", side="long", entry_price=60000.0, size_multiplier=1.0,
        timeframe="4h", fingerprint=_FP_A,
    )
    assert pos is not None and decision["allowed"] is True
    assert "reentry_guard" not in decision
