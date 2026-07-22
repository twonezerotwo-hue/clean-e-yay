"""cross_tf kilidi — owner problemi #6 (2026-07-21).

Sizinti: kilit (symbol, side, timeframe) anahtarindaydi; "BTC 1h karda kapandi"
4h adayini engellemiyordu. cross_tf=True anahtardan TF'i dusurur.
DEFAULT FALSE -> bayt-ayni (regresyon bekcisi ilk testte).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.paper import reentry_guard


class _T:
    def __init__(self, symbol, side, timeframe, closed_at, pnl_usd=10.0,
                 close_reason="TP_HIT", fingerprint="FP1"):
        self.symbol, self.side, self.timeframe = symbol, side, timeframe
        self.closed_at, self.pnl_usd = closed_at, pnl_usd
        self.close_reason, self.fingerprint = close_reason, fingerprint
        self.lifecycle_status = "CLOSED"


class _S:
    def __init__(self, trades): self.recent_trades = trades


_NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def _close_1h(**kw):
    # 1h pozisyon 10 dk once KARDA kapandi -> kilidi kurar
    return _T("BTCUSD", "long", "1h", (_NOW - timedelta(minutes=10)).isoformat(), **kw)


def test_default_off_is_byte_identical_cross_tf():
    """cross_tf yokken 4h adayi ETKILENMEZ (mevcut davranis korunur)."""
    rep = reentry_guard.assess(
        _S([_close_1h()]), symbol="BTCUSD", side="long", timeframe="4h",
        fingerprint="FP1", now=_NOW, cfg={"enabled": True},
    )
    assert rep == {}, "TF hapsindeyken 4h icin kilit kurulmamali"


def test_cross_tf_locks_other_timeframe():
    """cross_tf=True -> 1h karli kapanisi 4h adayini KILITLER (bayat sinyal)."""
    rep = reentry_guard.assess(
        _S([_close_1h()]), symbol="BTCUSD", side="long", timeframe="4h",
        fingerprint="FP1", now=_NOW, cfg={"enabled": True, "cross_tf": True},
    )
    assert rep["locked"] is True
    assert rep["cross_tf"] is True
    assert rep["armed_timeframe"] == "1h"
    assert "sinyal_ayni" in rep["reason"]


def test_cross_tf_releases_when_bar_fresh_and_signal_changed():
    """Iki kosul birden saglanirsa kilit ACILIR (kalici kilit degil)."""
    old = _T("BTCUSD", "long", "1h",
             (_NOW - timedelta(hours=9)).isoformat(), fingerprint="FP_OLD")
    rep = reentry_guard.assess(
        _S([old]), symbol="BTCUSD", side="long", timeframe="4h",
        fingerprint="FP_NEW", now=_NOW, cfg={"enabled": True, "cross_tf": True},
    )
    assert rep["fresh_bar"] is True and rep["signal_changed"] is True
    assert rep["locked"] is False


def test_cross_tf_opposite_side_never_locked():
    """Ters yon farkli anahtar -> dogal flip serbest kalir."""
    rep = reentry_guard.assess(
        _S([_close_1h()]), symbol="BTCUSD", side="short", timeframe="4h",
        fingerprint="FP1", now=_NOW, cfg={"enabled": True, "cross_tf": True},
    )
    assert rep == {}


def test_cross_tf_losing_close_does_not_arm():
    """Zararli otomatik kapanis kilit KURMAZ (mevcut kural cross_tf'te de gecerli)."""
    loss = _close_1h(pnl_usd=-40.0, close_reason="SL_HIT")
    rep = reentry_guard.assess(
        _S([loss]), symbol="BTCUSD", side="long", timeframe="4h",
        fingerprint="FP1", now=_NOW, cfg={"enabled": True, "cross_tf": True},
    )
    assert rep == {}
