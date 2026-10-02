"""Olay-sonrası takip (learning/event_outcomes) — salt-gözlem, karar zincirine girmez."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.data import snapshot_store
from packages.data.providers.calendar import release_time_utc
from packages.learning import event_outcomes as eo

CAL = """
events:
  - id: "nfp_test"
    date: "2026-10-02"
    name: "ABD İstihdam / NFP (Eylül 2026)"
    category: "MACRO"
    importance: "HIGH"
    expectation: "08:30 ET — BLS resmi takvim"
"""
REL = datetime(2026, 10, 2, 12, 30, tzinfo=UTC)
PRE = {"DXY": 100.0, "XAUUSD": 2000.0, "BTCUSD": 80000.0}


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_OUTCOMES_PATH", str(tmp_path / "event_outcomes.json"))
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path / "snapshots"))
    p = tmp_path / "cal.yaml"
    p.write_text(CAL, encoding="utf-8")
    return p


def _h(title: str, at: datetime) -> dict:
    return {"title": title, "ts": at.isoformat(), "source": "test", "verified": True}


def test_release_time_follows_us_eastern_dst():
    assert release_time_utc({"date": "2026-10-02", "expectation": "08:30 ET — BLS"})[0] == REL
    winter = release_time_utc({"date": "2026-12-04", "expectation": "08:30 ET"})
    assert winter[0] == datetime(2026, 12, 4, 13, 30, tzinfo=UTC)
    explicit = release_time_utc({"date": "2026-10-07", "time": "14:00 ET", "expectation": "x"})
    assert explicit == (datetime(2026, 10, 7, 18, 0, tzinfo=UTC), "time")
    assert release_time_utc({"date": "2026-10-07"})[1] == "default_noon"


def test_headline_votes_ignore_previews_and_foreign_data():
    assert eo.classify_headline("Bitcoin Reacts to Weaker-Than-Expected US Jobs Report", "jobs") == "low"
    assert eo.classify_headline("Treasury yields retreat after the softer September payrolls", "jobs") == "low"
    assert eo.classify_headline("Payrolls beat estimates as hiring stays robust", "jobs") == "high"
    assert eo.classify_headline("Bitcoin rises ahead of key U.S. jobs data", "jobs") is None
    assert eo.classify_headline("Eurozone inflation hits highest level in three years", "inflation") is None
    assert eo.classify_headline("Gold edges up on safe-haven demand", "jobs") is None


def test_lifecycle_baseline_outcome_reaction_and_single_notification(cal):
    # Açıklamadan önce: taban fiyat alınır, sonuç yok.
    assert eo.track(prices=PRE, headlines=[], now=REL - timedelta(minutes=5), calendar_path=cal) == []
    # Açıklama sonrası: önizleme + açıklama öncesi başlık sayılmaz; 2 zayıf başlık → ZAYIF.
    heads = [
        _h("Bitcoin rises ahead of key U.S. jobs data", REL - timedelta(minutes=20)),
        _h("Dollar falls after weaker-than-expected US payrolls", REL + timedelta(minutes=2)),
        _h("Bond traders pull back after soft jobs data", REL + timedelta(minutes=3)),
    ]
    notes = eo.track(prices=PRE, headlines=heads, now=REL + timedelta(minutes=5), calendar_path=cal)
    assert [n.type for n in notes] == ["event_outcome"]
    assert "ZAYIF" in notes[0].title
    # Aynı sonuç ikinci kez bildirilmez.
    assert eo.track(prices=PRE, headlines=heads, now=REL + timedelta(minutes=6), calendar_path=cal) == []
    moved = {"DXY": 99.8, "XAUUSD": 2020.0, "BTCUSD": 80400.0}
    eo.track(prices=moved, headlines=heads, now=REL + timedelta(minutes=16), calendar_path=cal)
    notes = eo.track(prices=moved, headlines=heads, now=REL + timedelta(minutes=61), calendar_path=cal)
    assert len(notes) == 1 and notes[0].title.startswith("Tepki (1 saat)")
    assert "3/3" in notes[0].body_short

    vm = eo.viewmodel(now=REL + timedelta(minutes=62), calendar_path=cal)
    rec = vm["recent"][0]
    assert rec["status"] == "MEASURING"
    assert rec["outcome"]["direction"] == "low"
    assert rec["expected"]["DXY"] == -1 and rec["expected"]["XAUUSD"] == 1
    assert rec["realized"]["15m"]["moves"]["DXY"] == pytest.approx(-0.2)
    assert rec["realized"]["15m"]["hits"]["hit"] == 3
    bucket = vm["summary"]["buckets"][0]
    assert (bucket["family"], bucket["direction"]) == ("jobs", "low")
    assert bucket["horizons"]["1h"]["hit_rate"] == 1.0


def _doc(at: datetime, prices: dict, headlines: list[dict] | None = None) -> dict:
    return {
        "snapshot_id": f"snap::{at:%H%M}",
        "generated_at": at.isoformat(),
        "data_snapshot": {"prices": [{"symbol": s, "price": p} for s, p in prices.items()]},
        "causal_reconstruction": {"headlines": headlines or []},
    }


def test_backfills_from_snapshot_store_when_system_was_down(cal):
    weak = [
        _h("Wall St rallies after weak payrolls", REL + timedelta(minutes=4)),
        _h("Gold rises as soft jobs data cuts hike odds", REL + timedelta(minutes=6)),
    ]
    snapshot_store.record(_doc(REL - timedelta(minutes=2), PRE))
    snapshot_store.record(_doc(REL + timedelta(minutes=16), {"DXY": 99.9, "XAUUSD": 2010.0}, weak))
    snapshot_store.record(_doc(REL + timedelta(minutes=62), {"DXY": 99.7, "XAUUSD": 1990.0}, weak))
    # Sistem 14:00'te açılıyor: canlı fiyat/başlık yok, depo var.
    eo.track(prices={}, headlines=[], now=REL + timedelta(minutes=90), calendar_path=cal)
    rec = eo.viewmodel(now=REL + timedelta(minutes=90), calendar_path=cal)["recent"][0]
    assert rec["baseline_source"] == "snapshot_store"
    assert rec["outcome"]["direction"] == "low"
    assert rec["realized"]["15m"]["source"] == "snapshot_store"
    assert rec["realized"]["1h"]["hits"]["per_asset"] == {"DXY": "hit", "XAUUSD": "miss"}


def test_no_calendar_event_means_no_state_write(cal, tmp_path):
    far = REL + timedelta(days=10)
    assert eo.track(prices=PRE, headlines=[], now=far, calendar_path=cal) == []
    assert not (tmp_path / "event_outcomes.json").exists()
