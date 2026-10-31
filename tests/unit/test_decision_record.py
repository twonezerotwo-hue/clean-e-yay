"""Kalıcı karar kaydı: checkpoint, yalnız değişen hücre, sürüm bilgisi, saklama, yedek."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.decision import record

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
SNAP = SimpleNamespace(snapshot_id="snap::1", quality=SimpleNamespace(status="OK"))


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RECORD_DIR", str(tmp_path / "decision_record"))
    monkeypatch.delenv("DECISION_RECORD_RETENTION_DAYS", raising=False)
    record.reset()
    yield
    record.reset()


def _d(symbol, tf="1h", action="hold", candidate="open_long", blocked=("ev_gate",), score=55.0):
    modules = [SimpleNamespace(name="fundamental", layer="context", raw=10.0, score=40.0, weight=0.2),
               SimpleNamespace(name="touche", layer="vote", raw=None, score=62.0, weight=0.4)]
    return SimpleNamespace(symbol=symbol, timeframe=tf, action=action, candidate_action=candidate,
                           consensus=SimpleNamespace(direction="bullish", modules=modules, dominant_module="touche"),
                           consensus_score=score,
                           confidence=0.4, expected_value=-0.2, blocked_by=list(blocked), decision_id=f"dec_{symbol}")


def _gate(route="block", blocker="technical_confirmation"):
    return SimpleNamespace(route=route, blocker=blocker, size_multiplier=0.0)


def test_first_tick_is_checkpoint_with_versions_then_only_changes():
    decisions = [_d("BTCUSD"), _d("ETHUSD")]
    gates = {("BTCUSD", "1h"): _gate(), ("ETHUSD", "1h"): _gate()}
    assert record.append(SNAP, decisions, gates, now=T0, risk_action="ALLOW") == {"kind": "checkpoint", "cells": 2}
    # Skor oynaması satır üretmez.
    assert record.append(SNAP, [_d("BTCUSD", score=56.0), _d("ETHUSD")], gates, now=T0 + timedelta(seconds=30))["kind"] == "none"
    # Rota değişen tek hücre yazılır.
    gates[("BTCUSD", "1h")] = _gate(route="open", blocker=None)
    out = record.append(SNAP, decisions, gates, now=T0 + timedelta(seconds=60))
    assert out == {"kind": "delta", "cells": 1}
    rows = record.load_day("2026-10-30")
    assert [r["kind"] for r in rows] == ["checkpoint", "delta"]
    assert rows[0]["versions"]["thresholds"] and rows[0]["risk_action"] == "ALLOW"
    assert rows[1]["cells"][0]["symbol"] == "BTCUSD" and rows[1]["cells"][0]["route"] == "open"
    assert rows[0]["cells"][0]["gate_blocker"] == "technical_confirmation" and rows[0]["cells"][0]["ev"] == -0.2
    path = rows[0]["cells"][0]
    assert [m["layer"] for m in path["modules"]] == ["context", "vote"]
    assert path["modules"][0] == {"name": "fundamental", "layer": "context", "raw": 10.0, "score": 40.0, "weight": 0.2}
    assert path["dominant"] == "touche"


def test_counters_inside_blocker_codes_do_not_create_rows():
    record.append(SNAP, [_d("XAUUSD", blocked=("market_closed:15m:4051s",))], {}, now=T0)
    out = record.append(SNAP, [_d("XAUUSD", blocked=("market_closed:15m:4082s",))], {}, now=T0 + timedelta(seconds=30))
    assert out["kind"] == "none"
    out = record.append(SNAP, [_d("XAUUSD", blocked=("ev_gate",))], {}, now=T0 + timedelta(seconds=60))
    assert out["kind"] == "delta"


def test_hourly_checkpoint_and_flag_change_force_full_copy(monkeypatch):
    decisions = [_d("BTCUSD")]
    record.append(SNAP, decisions, {}, now=T0)
    assert record.append(SNAP, decisions, {}, now=T0 + timedelta(minutes=61))["kind"] == "checkpoint"
    monkeypatch.setenv("LEARNING_ADVISOR_APPLY", "1")
    out = record.append(SNAP, decisions, {}, now=T0 + timedelta(minutes=62))
    assert out["kind"] == "checkpoint"
    assert record.load_day("2026-10-30")[-1]["versions"]["flags"]["LEARNING_ADVISOR_APPLY"] == "1"


def test_retention_removes_only_old_day_files(tmp_path):
    folder = tmp_path / "decision_record"
    folder.mkdir()
    (folder / "2026-09-01.jsonl").write_text("{}\n", encoding="utf-8")
    (folder / "2026-10-29.jsonl").write_text("{}\n", encoding="utf-8")
    (folder / "notlar.txt").write_text("x", encoding="utf-8")
    record.append(SNAP, [_d("BTCUSD")], {}, now=T0)
    assert not (folder / "2026-09-01.jsonl").exists()
    assert (folder / "2026-10-29.jsonl").exists() and (folder / "notlar.txt").exists()


def test_backup_includes_latest_record_days(tmp_path, monkeypatch):
    from packages.ops import backup

    folder = tmp_path / "decision_record"
    folder.mkdir()
    for day in ("2026-10-27", "2026-10-28", "2026-10-29"):
        (folder / f"{day}.jsonl").write_text('{"kind": "checkpoint"}\n', encoding="utf-8")
    names = [name for name, _ in backup._sources() if name.startswith("decision_record/")]
    assert names == ["decision_record/2026-10-28.jsonl", "decision_record/2026-10-29.jsonl"]
