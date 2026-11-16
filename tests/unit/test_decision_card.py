"""Karar kartı (karar-destek adım 2): owner'ın araçları biletin yanında, gözlemci.

Kabul:
- yapı yönü son iki tepe/dip ile (yukarı / aşağı / yatay) ve adayın yönüyle uyumu;
- önceki dip/tepe ve girişe ATR uzaklığı;
- Fib geri çekilme oranı, 0,382–0,618 bölgesi, uzantılar;
- pozisyon süresine düşen yalnız yüksek/kritik olaylar;
- karşı-olgu geçmişi aynı sembol × TF × yön, son 60 gün, değişen gün dosyası yeniden okunur;
- bir bölüm düşerse diğerleri ve bilet sürer; bilet kartı ``technical_detail.owner_card``'a yazar.
"""
from __future__ import annotations

import itertools
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.types import Catalyst, FibonacciAnalysis, FibonacciLevel, OHLCVBar
from packages.paper import decision_card as dc

_T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _bars(points: list[float], steps: int = 6, tf: str = "1h") -> list[OHLCVBar]:
    closes: list[float] = []
    for a, b in itertools.pairwise(points):
        for k in range(steps):
            closes.append(a + (b - a) * k / steps)
    closes.append(points[-1])
    return [
        OHLCVBar(symbol="TEST", timeframe=tf, ts=_T0 + timedelta(hours=i), open=c, high=c + 0.1,
                 low=c - 0.1, close=c, volume=1.0, source="test", verified=True)
        for i, c in enumerate(closes)
    ]


_UP = [100, 110, 105, 115, 110, 120, 115, 125, 122]
_DOWN = [125, 115, 120, 110, 115, 105, 110, 100, 103]
_RANGE = [100, 110, 104, 112, 102, 106]  # tepe yükseliyor, dip düşüyor


# ---------- yapı ----------

@pytest.mark.parametrize(("points", "direction"), [(_UP, "up"), (_DOWN, "down"), (_RANGE, "range")])
def test_structure_direction(points, direction) -> None:
    out = dc.structure(_bars(points), "4h", "long")
    assert out["status"] == "ok" and out["direction"] == direction
    assert out["aligned"] is (direction == "up")


def test_structure_alignment_for_short() -> None:
    assert dc.structure(_bars(_DOWN), "4h", "short")["aligned"] is True
    assert dc.structure(_bars(_UP), "4h", "short")["aligned"] is False


def test_structure_needs_bars_and_pivots() -> None:
    assert dc.structure([], "4h", "long") == {"status": "unavailable", "reason": "no_bars"}
    assert dc.structure(_bars([100, 101]), "4h", "long")["reason"] == "insufficient_pivots"


# ---------- önceki dip / tepe ----------

def test_swing_reports_last_pivots_in_atr() -> None:
    out = dc.swing(_bars(_UP), entry=122.0, atr=2.0)
    assert out["status"] == "ok"
    assert out["prev_low"] == pytest.approx(114.9, abs=0.01)   # son dip 115 (fitil 0,1)
    assert out["prev_high"] == pytest.approx(125.1, abs=0.01)
    assert out["prev_low_atr"] == pytest.approx((122 - 114.9) / 2, abs=0.01)
    assert out["prev_high_atr"] == pytest.approx((125.1 - 122) / 2, abs=0.01)


def test_swing_without_atr_keeps_prices() -> None:
    out = dc.swing(_bars(_UP), entry=122.0, atr=float("nan"))
    assert out["prev_low_atr"] is None and out["prev_low"] is not None


# ---------- Fib ----------

def _fake_fib(monkeypatch, trend: str) -> None:
    from packages.data.providers.technical import fibonacci

    levels = [
        FibonacciLevel(ratio=0.618, label="0.618", price=161.8, kind="retracement"),
        FibonacciLevel(ratio=1.272, label="1.272", price=227.2, kind="extension"),
        FibonacciLevel(ratio=1.618, label="1.618", price=261.8, kind="extension"),
    ]
    monkeypatch.setattr(fibonacci, "analyze", lambda bars, **kw: FibonacciAnalysis(
        timeframe="4H", swing_high=200.0, swing_low=100.0, trend_direction=trend, levels=levels,
        zone="mid_range", validity="sane",
    ))


@pytest.mark.parametrize(("trend", "entry", "ratio", "zone"), [
    ("uptrend", 150.0, 0.5, True), ("uptrend", 180.0, 0.2, False), ("uptrend", 130.0, 0.7, False),
    ("downtrend", 150.0, 0.5, True), ("downtrend", 110.0, 0.1, False),
])
def test_fib_retracement_and_golden_zone(monkeypatch, trend, entry, ratio, zone) -> None:
    _fake_fib(monkeypatch, trend)
    out = dc.fib(_bars(_UP), "4H", entry)
    assert out["retracement"] == pytest.approx(ratio)
    assert out["in_golden_zone"] is zone
    assert [e["ratio"] for e in out["extensions"]] == [1.272, 1.618]


def test_fib_range_has_no_ratio(monkeypatch) -> None:
    _fake_fib(monkeypatch, "range")
    out = dc.fib(_bars(_UP), "4H", 150.0)
    assert out["retracement"] is None and out["in_golden_zone"] is False


# ---------- 0-2 ----------

def test_zero_two_line_runs_on_real_bars() -> None:
    out = dc.zero_two_line(_bars(_UP), "long")
    assert out["status"] == "ok"
    if out["found"]:
        assert out["direction"] in {"up", "down"} and isinstance(out["line_price"], float)
    assert dc.zero_two_line([], "long")["status"] == "unavailable"


# ---------- olaylar ----------

def _cat(cid: str, hours: float, importance: str) -> Catalyst:
    return Catalyst(id=cid, ts=_T0 + timedelta(hours=hours), title=cid, importance=importance)


def test_events_only_important_inside_hold_window() -> None:
    cats = [_cat("cpi", 5, "critical"), _cat("pmi", 2, "high"), _cat("minor", 1, "low"),
            _cat("late", 30, "critical"), _cat("past", -1, "high")]
    out = dc.events(cats, _T0, 24.0)
    assert [e["title"] for e in out["items"]] == ["pmi", "cpi"]
    assert out["items"][1]["hours_until"] == 5.0 and out["hold_hours"] == 24.0


def test_hold_hours_uses_time_stop_else_eight_bars(monkeypatch) -> None:
    from packages.paper import lifecycle

    monkeypatch.setattr(lifecycle, "_timeframe_time_stop_hours", lambda tf: 0)
    assert dc.hold_hours("4h") == 32.0
    monkeypatch.setattr(lifecycle, "_timeframe_time_stop_hours", lambda tf: 12)
    assert dc.hold_hours("4h") == 12.0


# ---------- karşı-olgu geçmişi ----------

def _write(path, rows) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_history_aggregates_same_key_last_60_days(tmp_path) -> None:
    key = {"symbol": "BTCUSD", "timeframe": "1h", "side": "long"}
    _write(tmp_path / "2026-11-16.jsonl", [
        {**key, "net_r": 1.5}, {**key, "net_r": -1.0}, {**key, "net_r": None},
        {**key, "side": "short", "net_r": 2.0}, {"symbol": "ETHUSD", "timeframe": "1h", "side": "long", "net_r": 3.0},
    ])
    _write(tmp_path / "2026-11-01.jsonl", [{**key, "net_r": -0.5}])
    _write(tmp_path / "2026-08-01.jsonl", [{**key, "net_r": 9.0}])  # 60 günden eski
    (tmp_path / "2026-11-02.jsonl").write_text("bozuk satır\n", encoding="utf-8")
    out = dc.history("BTCUSD", "1h", "long", _T0, tmp_path)
    assert out["n"] == 3
    assert out["mean_net_r"] == pytest.approx(0.0)
    assert out["win_rate"] == pytest.approx(1 / 3, abs=1e-3)


def test_history_rereads_changed_day_file(tmp_path) -> None:
    key = {"symbol": "XAUUSD", "timeframe": "4h", "side": "short"}
    day = tmp_path / "2026-11-16.jsonl"
    _write(day, [{**key, "net_r": 1.0}])
    assert dc.history("XAUUSD", "4h", "short", _T0, tmp_path)["n"] == 1
    _write(day, [{**key, "net_r": 1.0}, {**key, "net_r": -2.0}])
    st = day.stat()
    os.utime(day, (st.st_atime, st.st_mtime + 5))
    out = dc.history("XAUUSD", "4h", "short", _T0, tmp_path)
    assert out["n"] == 2 and out["mean_net_r"] == pytest.approx(-0.5)


def test_history_without_ledger(tmp_path) -> None:
    assert dc.history("X", "1h", "long", _T0, tmp_path / "yok")["status"] == "unavailable"


# ---------- kartın tamamı ----------

def test_card_survives_missing_bars(tmp_path) -> None:
    card = dc.build_owner_card("BTCUSD", "1h", "long", 60_000.0, 500.0, now=_T0,
                               bars_fn=lambda s, tf: [], ledger_dir=tmp_path)
    for name in ("structure", "swing", "fib", "zero_two"):
        assert card[name] == {"status": "unavailable", "reason": "no_bars"}
    assert card["events"]["status"] == "ok" and card["history"]["status"] == "ok"


def test_card_isolates_a_failing_section(tmp_path) -> None:
    def boom(symbol, tf):
        raise RuntimeError("feed down")

    card = dc.build_owner_card("BTCUSD", "1h", "long", 60_000.0, 500.0, now=_T0,
                               bars_fn=boom, ledger_dir=tmp_path)
    assert card["structure"] == {"status": "unavailable", "reason": "error:RuntimeError"}
    assert card["history"]["status"] == "ok"


def test_card_reads_higher_tf_and_fib_frame(tmp_path) -> None:
    asked: list[str] = []

    def bars_fn(symbol, tf):
        asked.append(tf)
        return _bars(_UP, tf=tf)

    dc.build_owner_card("BTCUSD", "1h", "long", 122.0, 1.0, now=_T0, bars_fn=bars_fn, ledger_dir=tmp_path)
    assert sorted(set(asked)) == ["1h", "4h"]  # üst TF 4h + Fib 4H; aday TF 1h (her biri bir kez)
    asked.clear()
    dc.build_owner_card("BTCUSD", "1d", "long", 122.0, 1.0, now=_T0, bars_fn=bars_fn, ledger_dir=tmp_path)
    assert sorted(set(asked)) == ["1d", "1w"]


# ---------- bilet entegrasyonu ----------

@pytest.mark.usefixtures("seed_ohlcv_reference")
def test_ticket_carries_owner_card(monkeypatch) -> None:
    from packages.paper import state as paper_state
    from packages.paper import ticket

    seen = {}

    def fake_card(symbol, timeframe, side, entry, atr, **kw):
        seen.update(symbol=symbol, timeframe=timeframe, side=side, entry=entry, atr=atr, **kw)
        return {"version": 1, "stub": True}

    monkeypatch.setattr(ticket.decision_card, "build_owner_card", fake_card)
    module = SimpleNamespace(name="touche", score=70.0, weight=1.0, contribution=0.2)
    decision = SimpleNamespace(
        action="open_long", candidate_action="open_long", symbol="BTCUSD", timeframe="1d",
        fingerprint="fp", confidence=0.6, raw_confidence=0.6, confidence_source="test", reason="r",
        consensus=SimpleNamespace(score=70.0, direction="bullish", confluence_aligned=True,
                                  dominant_module="touche", modules=[module], warnings=[]),
        risk=SimpleNamespace(action="ALLOW", reason="", evidence=[]), blocked_by=[], size_multiplier=1.0,
        mistake_verdict=None, derivatives_report=None, volatility_report=None, catalyst_report=None,
        options_report=None, engine="test",
    )
    tech = SimpleNamespace(atr=1_500.0, rsi=55.0, macd=0.0, ema_stack="bull", score=60.0, status="OK")
    snap = SimpleNamespace(
        prices=[SimpleNamespace(symbol="BTCUSD", price=60_000.0)], technicals_by_tf={"BTCUSD": {"1d": tech}},
        technicals={}, quality=SimpleNamespace(score=90.0), snapshot_id="snap-1",
        catalysts=[_cat("cpi", 5, "critical")],
    )
    tk = ticket.build_ticket(decision, snap, paper_state._initial_state())
    assert tk.technical_detail["owner_card"] == {"version": 1, "stub": True}
    assert seen["symbol"] == "BTCUSD" and seen["side"] == "long" and seen["atr"] == 1_500.0
    assert seen["entry"] == 60_000.0 and len(seen["catalysts"]) == 1
