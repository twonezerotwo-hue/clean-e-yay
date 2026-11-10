"""Kapı karşı-olgu defteri: aday açılsaydı plan stop/hedefiyle ne olurdu (salt ölçüm)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.decision import record
from packages.learning import gate_counterfactual as gcf

T0 = datetime(2026, 11, 10, 6, 10, tzinfo=UTC)  # karar anı (06:00 barının içi)
PLAN = {"price": 100.0, "sl_pct": 0.01, "tp_pct": 0.02, "time_stop_h": 48.0, "basis": "atr"}


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RECORD_DIR", str(tmp_path / "decision_record"))
    monkeypatch.delenv("DECISION_RECORD_RETENTION_DAYS", raising=False)
    record.reset()
    yield
    record.reset()


def _bars(*ohlc, start=datetime(2026, 11, 10, 7, 0, tzinfo=UTC), step=timedelta(hours=1)):
    return gcf.bar_rows([SimpleNamespace(ts=start + i * step, open=o, high=h, low=lo, close=c)
                         for i, (o, h, lo, c) in enumerate(ohlc)])


def _sample(side="long", plan=PLAN, tf="1h"):
    return {"ts": T0.isoformat(), "decision_id": "dec_1", "symbol": "BTCUSD", "timeframe": tf, "side": side,
            "action": "hold", "route": "block", "final_blocker": "no_candidate", "blocked_by": ["ev_gate"],
            "opened": False, "score": 60.0, "confidence": 0.4, "ev": -0.1, "plan": plan}


FLAT = (100.0, 100.5, 99.5, 100.0)
LATE = T0 + timedelta(days=5)


def test_long_target_hit_is_plus_rr():
    row = gcf.resolve(_sample(), _bars(FLAT, (100.0, 102.5, 99.6, 102.0), *[FLAT] * 6), LATE)
    assert row["outcome"] == "tp" and row["r"] == 2.0 and row["net_r"] < 2.0
    assert row["entry_ts"] == "2026-11-10T07:00:00+00:00" and row["entry"] == 100.0
    assert row["blocked_by"] == ["ev_gate"] and row["horizon_bars"] == 8


def test_both_levels_in_one_bar_counts_as_stop():
    row = gcf.resolve(_sample(), _bars((100.0, 103.0, 98.0, 101.0), *[FLAT] * 7), LATE)
    assert row["outcome"] == "sl" and row["r"] == -1.0


def test_gap_through_stop_exits_at_open():
    row = gcf.resolve(_sample(side="short"), _bars(FLAT, (103.0, 104.0, 102.5, 103.5), *[FLAT] * 6), LATE)
    assert row["outcome"] == "sl" and row["r"] == -3.0


def test_time_stop_waits_for_real_time_then_exits_at_last_close():
    bars = _bars(*[FLAT] * 9, (100.0, 100.5, 99.5, 100.4), *[FLAT] * 40)
    plan = {**PLAN, "time_stop_h": 10.0}
    assert gcf.resolve(_sample(plan=plan), bars, T0 + timedelta(hours=8)) is None
    row = gcf.resolve(_sample(plan=plan), bars, T0 + timedelta(hours=20))
    assert row["outcome"] == "time" and row["exit_bar_ts"] == "2026-11-10T16:00:00+00:00"
    assert row["r"] == pytest.approx(0.4)


def test_not_enough_bars_waits_and_old_record_without_plan_gets_horizon_return_only():
    assert gcf.resolve(_sample(), _bars(*[FLAT] * 3), LATE) is None
    row = gcf.resolve(_sample(side="short", plan=None), _bars(*[FLAT] * 7, (100.0, 100.0, 98.0, 99.0)), LATE)
    assert row["ret_pct"] == 1.0 and row["outcome"] is None and row["r"] is None


def _cell(symbol, candidate="open_long", tf="1h", **extra):
    return {"symbol": symbol, "timeframe": tf, "candidate": candidate, "action": "hold", "route": "block",
            "gate_blocker": "no_candidate", "blocked_by": ["ev_gate"], "decision_id": f"dec_{symbol}",
            "plan": PLAN, **extra}


def test_run_reads_from_cursor_skips_partial_line_and_never_writes_twice(monkeypatch):
    folder = record._dir()
    folder.mkdir(parents=True)
    rows = [{"ts": T0.isoformat(), "kind": "checkpoint",
             "cells": [_cell("BTCUSD"), _cell("BTCUSD", candidate=None), _cell("BTCUSD", tf="1w")]},
            {"ts": (T0 + timedelta(minutes=20)).isoformat(), "kind": "delta", "cells": [_cell("BTCUSD")]}]
    day = folder / "2026-11-10.jsonl"
    day.write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"ts": "yar', encoding="utf-8")
    bars = _bars(FLAT, (100.0, 102.5, 99.6, 102.0), *[FLAT] * 6)
    monkeypatch.setattr(gcf, "_bars", lambda symbol, tf, memo: bars)

    assert gcf.run(now=LATE) == {"status": "OK", "new": 1, "resolved": 1, "pending": 0, "dropped": 0}
    out = gcf.load_day("2026-11-10")
    assert len(out) == 1 and out[0]["outcome"] == "tp" and out[0]["decision_id"] == "dec_BTCUSD"
    state = json.loads((gcf._dir() / "state.json").read_text(encoding="utf-8"))
    assert state["day"] == "2026-11-10" and state["line"] == 2  # yarım satır okunmadı

    # Yarım satır tamamlanınca okunur; aynı giriş barı ikinci kez yazılmaz.
    later = {"ts": (T0 + timedelta(minutes=40)).isoformat(), "kind": "delta", "cells": [_cell("BTCUSD")]}
    day.write_text("".join(json.dumps(r) + "\n" for r in [*rows, later]), encoding="utf-8")
    assert gcf.run(now=LATE)["resolved"] == 0
    assert len(gcf.load_day("2026-11-10")) == 1


def test_record_keeps_open_time_plan_only_for_candidate_cells():
    snap = SimpleNamespace(
        snapshot_id="snap::1", quality=SimpleNamespace(status="OK"),
        prices=[SimpleNamespace(symbol="BTCUSD", price=100.0), SimpleNamespace(symbol="ETHUSD", price=50.0)],
        technicals_by_tf={"BTCUSD": {"1h": SimpleNamespace(atr=1.5)}},
    )
    modules = [SimpleNamespace(name="touche", layer="vote", raw=None, score=62.0, weight=0.4)]

    def dec(symbol, candidate):
        return SimpleNamespace(symbol=symbol, timeframe="1h", action="hold", candidate_action=candidate,
                               consensus=SimpleNamespace(direction="bullish", modules=modules, dominant_module="touche"),
                               consensus_score=60.0, confidence=0.4, expected_value=-0.2, blocked_by=["ev_gate"],
                               decision_id=f"dec_{symbol}")

    record.append(snap, [dec("BTCUSD", "open_long"), dec("ETHUSD", None)], {}, now=T0)
    cells = {c["symbol"]: c for c in record.load_day("2026-11-10")[0]["cells"]}
    plan = cells["BTCUSD"]["plan"]
    assert plan["price"] == 100.0 and 0 < plan["sl_pct"] < plan["tp_pct"] and plan["time_stop_h"] > 0
    assert "plan" not in cells["ETHUSD"]
