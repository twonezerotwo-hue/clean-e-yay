"""P2 — kapanış-bazlı stop lifecycle entegrasyonu testleri.

Kritik güvenceler:
- `_last_closed_close`: forming (kapanmamış) bar ATLANIR — son KAPANMIŞ bar döner.
- Flag kapalı → SL tetikleme fitil (tick), BAYT-AYNI mevcut davranış.
- Flag açık → fitil stop'u delse bile bar KAPANIŞI delmedikçe pozisyon AÇIK kalır.
- Fallback: kapanış okunamıyorsa fitil davranışına düşer (uydurma yok).
"""
from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.types import OHLCVBar
from packages.paper import lifecycle


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    from packages.paper import state as ps
    importlib.reload(ps)
    return ps


def _bar(ts, close):
    return OHLCVBar(symbol="BTCUSD", timeframe="4h", ts=ts, open=close,
                    high=close + 1, low=close - 1, close=close, volume=1.0)


class _Cached:
    def __init__(self, bars):
        self.bars = bars
        self.age_seconds = 0.0


def test_last_closed_close_skips_forming_bar(monkeypatch):
    """Son bar forming (açılış+TF henüz geçmedi) → bir önceki KAPANMIŞ bar kapanışı."""
    now = datetime(2026, 7, 10, 10, 0, tzinfo=UTC)
    # 4h barlar: -8h (kapandı, close 100), -4h (kapandı, close 101), -1h açılan (forming, 999)
    bars = [
        _bar(now - timedelta(hours=8), 100.0),
        _bar(now - timedelta(hours=4), 101.0),
        _bar(now - timedelta(hours=1), 999.0),   # forming: açılış+4h > now
    ]
    monkeypatch.setattr(lifecycle, "load_thresholds", lambda: {})  # cfg erişimi güvenli
    import packages.data.providers.ohlcv.cache as cache
    monkeypatch.setattr(cache, "load", lambda s, tf: _Cached(bars))
    v = lifecycle._last_closed_close("BTCUSD", "4h", now)
    assert v == 101.0   # forming (999) atlandı, son kapanmış 101


def test_last_closed_close_none_when_no_cache(monkeypatch):
    """Cache yok → None (çağıran fitil davranışına düşer)."""
    import packages.data.providers.ohlcv.cache as cache
    monkeypatch.setattr(cache, "load", lambda s, tf: None)
    assert lifecycle._last_closed_close("BTCUSD", "4h", datetime.now(UTC)) is None


def test_last_closed_close_unknown_tf_none():
    assert lifecycle._last_closed_close("BTCUSD", "3m", datetime.now(UTC)) is None


def _open_long(ps, fresh_env, *, entry=100.0, sl=95.0, tp=120.0):
    pos = ps.Position(
        id="p-BTCUSD-4h-long", symbol="BTCUSD", side="long", entry_price=entry,
        current_price=entry, size_usd=1000.0, sl=sl, tp=tp,
        opened_at="2026-07-10T00:00:00+00:00", timeframe="4h",
    )
    st = fresh_env.load()
    st.open_positions.append(pos)
    return st, pos


def test_flag_off_wick_triggers_sl(fresh_env, monkeypatch):
    """Flag kapalı: tick (fitil) 94 stop 95'i deldi → SL_HIT (mevcut davranış)."""
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: False)
    st, _pos = _open_long(fresh_env, fresh_env)
    closed = lifecycle.tick(st, {"BTCUSD": 94.0})
    assert len(closed) == 1 and closed[0].close_reason == "SL_HIT"


def test_flag_on_wick_survives_when_close_above_stop(fresh_env, monkeypatch):
    """Flag açık: tick fitil 94 stop 95'i delse de son KAPANIŞ 97 (stop üstü) → AÇIK kalır."""
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: True)
    monkeypatch.setattr(lifecycle, "_last_closed_close", lambda s, tf, now: 97.0)
    st, _pos = _open_long(fresh_env, fresh_env)
    closed = lifecycle.tick(st, {"BTCUSD": 94.0})
    assert closed == []                     # fitil-avına yem OLMADI
    assert _pos in st.open_positions


def test_flag_on_close_breach_triggers_sl(fresh_env, monkeypatch):
    """Flag açık: son KAPANIŞ 94 stop 95'i geçti → SL_HIT (fitil delmese bile)."""
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: True)
    monkeypatch.setattr(lifecycle, "_last_closed_close", lambda s, tf, now: 94.0)
    st, _pos = _open_long(fresh_env, fresh_env)
    closed = lifecycle.tick(st, {"BTCUSD": 96.0})   # tick stop üstünde ama kapanış altında
    assert len(closed) == 1 and closed[0].close_reason == "SL_HIT"


def test_flag_on_tp_still_wick(fresh_env, monkeypatch):
    """Flag açık: TP hâlâ tick (fitil) ile — kâr al fitille (owner kuralı)."""
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: True)
    monkeypatch.setattr(lifecycle, "_last_closed_close", lambda s, tf, now: 100.0)
    st, _pos = _open_long(fresh_env, fresh_env)
    closed = lifecycle.tick(st, {"BTCUSD": 121.0})   # tick TP 120'yi geçti
    assert len(closed) == 1 and closed[0].close_reason == "TP_HIT"


def test_flag_on_no_close_falls_back_to_wick(fresh_env, monkeypatch):
    """Flag açık ama kapanış okunamıyor (None) → fitil davranışına düşer (güvenli)."""
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: True)
    monkeypatch.setattr(lifecycle, "_last_closed_close", lambda s, tf, now: None)
    st, _pos = _open_long(fresh_env, fresh_env)
    closed = lifecycle.tick(st, {"BTCUSD": 94.0})
    assert len(closed) == 1 and closed[0].close_reason == "SL_HIT"
