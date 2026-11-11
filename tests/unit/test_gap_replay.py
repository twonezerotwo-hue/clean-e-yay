"""Uyku/kesinti telafisi: tick, son yönetimden (`marked_at`) bu yana tamamen kapanmış
barları canlı çıkış kurallarıyla oynatır; normal çalışmada hiçbir şey değişmez."""
from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers.ohlcv import cache as ohlcv_cache
from packages.data.types import OHLCVBar
from packages.paper import audit, lifecycle

T0 = datetime(2026, 7, 10, tzinfo=UTC)
NOW = T0 + timedelta(hours=8, minutes=5)          # uyanış
MARKED = (T0 + timedelta(hours=2, minutes=10)).isoformat()  # son yönetim (02:00 barı yarım görüldü)
FLAT = (100.0, 100.5, 99.5, 100.0)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    monkeypatch.setenv("OHLCV_CACHE_DIR", str(tmp_path / "ohlcv"))
    from packages.data.guards import price_sanity
    monkeypatch.setattr(price_sanity, "ohlcv_reference_price", lambda s, tf="15m": (None, None))
    events: list[dict] = []
    real = audit.record
    monkeypatch.setattr(audit, "record", lambda action, **f: events.append({"action": action, **f}) or real(action, **f))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps, events


def _save(tf: str, ohlc_by_hour: dict[int, tuple[float, float, float, float]], *, hours: int = 9) -> None:
    sec = {"1h": 3600, "4h": 14400}[tf]
    bars = []
    for h in range(0, hours, sec // 3600):
        o, hi, lo, c = ohlc_by_hour.get(h, FLAT)
        bars.append(OHLCVBar(symbol="BTCUSD", timeframe=tf, ts=T0 + timedelta(hours=h),
                             open=o, high=hi, low=lo, close=c, volume=1.0))
    ohlcv_cache.save("BTCUSD", tf, bars)


def _pos(ps, *, tf="1h", marked_at=MARKED, **kw):
    pos = ps.Position(
        id="gap-1", symbol="BTCUSD", side="long", entry_price=100.0, current_price=100.0,
        size_usd=1000.0, sl=98.0, tp=104.0, opened_at=T0.isoformat(), timeframe=tf,
        marked_at=marked_at, **kw,
    )
    st = ps.load()
    st.open_positions.append(pos)
    return st, pos


def test_disaster_during_gap_fills_at_level_not_at_wake_price(env):
    ps, events = env
    _save("1h", {5: (99.0, 99.5, 95.0, 95.5)})          # fitil acil frenin (96) altına indi
    st, _ = _pos(ps)
    closed = lifecycle.tick(st, {"BTCUSD": 101.0}, now=NOW)  # uyanışta fiyat toparlanmış
    assert len(closed) == 1
    t = closed[0]
    assert (t.close_reason, t.exit_price) == ("SL_HIT", 96.0)
    assert t.closed_at.startswith("2026-07-10T06:00")
    assert [e["action"] for e in events][:2] == ["GAP_REPLAY", "DISASTER_STOP"]


def test_crash_held_through_wake_is_capped_at_disaster_level(env):
    ps, _ = env
    _save("1h", {5: (99.0, 99.5, 90.0, 91.0), 6: (91.0, 92.0, 85.0, 86.0), 7: (86.0, 87.0, 84.0, 85.0)})
    st, _ = _pos(ps)
    closed = lifecycle.tick(st, {"BTCUSD": 85.0}, now=NOW)  # telafisiz: 85'ten −7,5R
    assert closed[0].exit_price == 96.0                       # telafiyle: −2R


def test_close_based_stop_during_gap_fills_at_bar_close(env):
    ps, _ = env
    _save("1h", {5: (99.0, 99.2, 97.0, 97.5)})          # fitil SL altı, kapanış SL altı, fren üstü
    st, _ = _pos(ps)
    t = lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW)[0]
    assert (t.close_reason, t.exit_price) == ("SL_HIT", 97.5)
    assert t.closed_at.startswith("2026-07-10T06:00")   # kapanış bir sonraki bar sınırında görülür


def test_take_profit_during_gap(env):
    ps, _ = env
    _save("1h", {5: (100.0, 104.5, 99.8, 104.2)})
    st, _ = _pos(ps)
    t = lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW)[0]
    assert (t.close_reason, t.exit_price) == ("TP_HIT", 104.0)


def test_trailing_during_gap(env):
    ps, _ = env
    _save("1h", {4: (100.0, 102.0, 99.9, 101.8), 5: (101.8, 101.9, 100.5, 100.7)})
    st, _ = _pos(ps, trail_distance_pct=0.01, trail_activate_pct=0.01, trail_peak=100.0)
    t = lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW)[0]
    assert t.close_reason == "TRAILING_STOP_EXIT"
    assert t.exit_price == pytest.approx(102.0 * 0.99, abs=1e-4)


def test_time_stop_during_gap_closes_at_next_bar_open(env):
    ps, _ = env
    _save("1h", {6: (100.3, 100.6, 100.1, 100.4)})
    st, _ = _pos(ps, valid_until=(T0 + timedelta(hours=5, minutes=30)).isoformat())
    t = lifecycle.tick(st, {"BTCUSD": 101.0}, now=NOW)[0]
    assert (t.close_reason, t.exit_price) == ("TIME_STOP_EXIT", 100.3)
    assert t.closed_at.startswith("2026-07-10T06:00")


def test_wick_stop_when_position_tf_has_no_cache(env):
    """4h önbelleği yok (canlıda kripto dışı) → canlıdaki gibi fitil stopu, 1h yol."""
    ps, _ = env
    _save("1h", {5: (99.0, 99.2, 97.5, 99.0)})
    st, _ = _pos(ps, tf="4h")
    t = lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW)[0]
    assert (t.close_reason, t.exit_price) == ("SL_HIT", 98.0)


def test_survivor_advances_excursions_and_marks_now(env):
    ps, events = env
    _save("1h", {4: (100.0, 100.8, 99.9, 100.2)})
    st, pos = _pos(ps)
    assert lifecycle.tick(st, {"BTCUSD": 100.2}, now=NOW) == []
    assert pos.mfe_pct == pytest.approx(0.8)
    assert pos.marked_at == NOW.isoformat()
    replay = [e for e in events if e["action"] == "GAP_REPLAY"]
    assert replay and replay[0]["reason"] == "no_exit" and replay[0]["bars"] == 5


def test_no_gap_no_replay(env):
    """Normal 30 sn tick: arada tamamen kapanmış bar yok → telafi çalışmaz."""
    ps, events = env
    _save("1h", {5: (99.0, 99.5, 90.0, 91.0)})
    st, _ = _pos(ps, marked_at=(NOW - timedelta(seconds=30)).isoformat())
    assert lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW) == []
    assert not [e for e in events if e["action"] == "GAP_REPLAY"]


def test_legacy_position_without_mark_is_not_replayed(env):
    ps, events = env
    _save("1h", {5: (99.0, 99.5, 90.0, 91.0)})
    st, pos = _pos(ps, marked_at=None)
    assert lifecycle.tick(st, {"BTCUSD": 100.0}, now=NOW) == []
    assert pos.marked_at == NOW.isoformat()
    assert not [e for e in events if e["action"] == "GAP_REPLAY"]
