"""H1 / H2 / H3 — stop yürütme hataları (temizlik raporu, Faz 1).

H1: kapanış-bazlı stop, açılıştan ÖNCE kapanmış veya bayat bar ile tetiklenmez.
H2: kapanış beklenirken fiyat açılış riskinin 2 katına kaçarsa acil fren çeker.
H3: önceki tick'e göre büyük sıçrama + OHLCV'den büyük sapma = bozuk tick, yok sayılır.
"""
from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest

from packages.data.guards import price_sanity
from packages.data.types import OHLCVBar
from packages.paper import lifecycle


class _Cached:
    def __init__(self, bars):
        self.bars = bars
        self.age_seconds = 0.0


def _bar(ts, close, tf="1d"):
    return OHLCVBar(symbol="BTCUSD", timeframe=tf, ts=ts, open=close,
                    high=close, low=close, close=close, volume=1.0)


@pytest.fixture
def cache_bars(monkeypatch):
    import packages.data.providers.ohlcv.cache as cache

    holder: dict = {"bars": []}
    monkeypatch.setattr(cache, "load", lambda s, tf: _Cached(holder["bars"]))
    return holder


# ── H1 ──────────────────────────────────────────────────────────────────────

def test_h1_bar_closed_before_open_cannot_trigger(cache_bars):
    now = datetime(2026, 7, 3, 20, 57, tzinfo=UTC)
    # Önceki günün 1d barı 7/3 00:00'da kapandı (62,755); pozisyon 20:56'da açıldı.
    cache_bars["bars"] = [_bar(datetime(2026, 7, 2, tzinfo=UTC), 62_755.0)]
    opened = "2026-07-03T20:56:00+00:00"
    assert lifecycle._last_closed_close("BTCUSD", "1d", now, opened) is None
    # Açılış verilmezse eski davranış (kapanış döner).
    assert lifecycle._last_closed_close("BTCUSD", "1d", now) == 62_755.0


def test_h1_bar_closed_after_open_is_used(cache_bars):
    now = datetime(2026, 7, 5, 1, 0, tzinfo=UTC)
    cache_bars["bars"] = [_bar(datetime(2026, 7, 4, tzinfo=UTC), 66_000.0)]  # 7/5 00:00 kapandı
    opened = "2026-07-03T20:56:00+00:00"
    assert lifecycle._last_closed_close("BTCUSD", "1d", now, opened) == 66_000.0


def test_h1_stale_cache_is_ignored(cache_bars):
    now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    # Son kapanmış bar 5 gün önce kapanmış (cache güncellenmemiş) → None.
    cache_bars["bars"] = [_bar(datetime(2026, 7, 4, tzinfo=UTC), 60_000.0)]
    assert lifecycle._last_closed_close("BTCUSD", "1d", now, "2026-07-01T00:00:00+00:00") is None


# ── H2 ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "paper.json"))
    from packages.paper import state as ps

    importlib.reload(ps)
    return ps


def _pos(ps, side="long", entry=100.0, sl=95.0, tp=120.0):
    st = ps.load()
    pos = ps.Position(
        id=f"p-{side}", symbol="BTCUSD", side=side, entry_price=entry, current_price=entry,
        size_usd=1000.0, sl=sl, tp=tp, opened_at="2026-07-10T00:00:00+00:00", timeframe="4h",
    )
    st.open_positions.append(pos)
    return st, pos


@pytest.mark.parametrize(
    ("side", "entry", "sl", "tp", "inside", "beyond"),
    [
        ("long", 100.0, 95.0, 120.0, 92.0, 89.9),    # acil fren: 90
        ("short", 100.0, 105.0, 80.0, 108.0, 110.1),  # acil fren: 110
    ],
)
def test_h2_disaster_stop(fresh_state, monkeypatch, side, entry, sl, tp, inside, beyond):
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: True)
    monkeypatch.setattr(lifecycle, "_disaster_stop_mult", lambda: 2.0)
    # Son kapanış stopun lehte tarafında → kapanış-bazlı SL tetiklenmez.
    monkeypatch.setattr(
        lifecycle, "_last_closed_close", lambda s, tf, now, opened_at=None: entry
    )
    monkeypatch.setattr(price_sanity, "tick_price_usable", lambda *a, **k: True)
    st, _pos_obj = _pos(fresh_state, side, entry, sl, tp)

    assert lifecycle.tick(st, {"BTCUSD": inside}) == []  # fitil SL'yi deldi, fren değil
    closed = lifecycle.tick(st, {"BTCUSD": beyond})
    assert len(closed) == 1 and closed[0].close_reason == "SL_HIT"
    assert closed[0].exit_price == beyond


def test_h2_inactive_when_close_based_stop_off(fresh_state, monkeypatch):
    monkeypatch.setattr(lifecycle, "_close_based_stop_enabled", lambda: False)
    st, _ = _pos(fresh_state)
    closed = lifecycle.tick(st, {"BTCUSD": 94.0})  # düz fitil SL (95) — eski davranış
    assert len(closed) == 1 and closed[0].exit_price == 94.0


def test_h2_mult_floor():
    class P:  # minimal pozisyon
        side, entry_price, sl = "long", 100.0, 95.0
    assert lifecycle._disaster_level(P, 1.0) == 95.0
    assert lifecycle._disaster_level(P, 2.0) == 90.0


# ── H3 ──────────────────────────────────────────────────────────────────────

def test_h3_bad_tick_rejected_until_reference_catches_up(monkeypatch):
    ref = {"v": 87.0}
    monkeypatch.setattr(price_sanity, "ohlcv_reference_price", lambda s, tf="15m": (ref["v"], "ohlcv:15m"))
    # BRENT vakası: 86.98 → 100.13 (%15) ve OHLCV 87 → bozuk kote.
    assert price_sanity.tick_price_usable("BRENT", 100.13, last_price=86.98) is False
    # Gerçek hareketse OHLCV cache yetişir → kabul.
    ref["v"] = 99.5
    assert price_sanity.tick_price_usable("BRENT", 100.13, last_price=86.98) is True


def test_h3_normal_moves_unaffected(monkeypatch):
    monkeypatch.setattr(price_sanity, "ohlcv_reference_price", lambda s, tf="15m": (None, None))
    assert price_sanity.tick_price_usable("BRENT", 90.0, last_price=86.98) is True
    assert price_sanity.tick_price_usable("BRENT", 100.13, last_price=86.98) is True  # ref yok
    assert price_sanity.tick_price_usable("BRENT", 200.0, last_price=86.98) is False  # >%30
