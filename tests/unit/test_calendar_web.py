"""Herkese açık beklenti takvimi (ForexFactory haftalık JSON): ayrıştırma, disk önbelleği, hata yolu."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from packages.data.providers.calendar import web

SAMPLE = [
    {"title": "CPI m/m", "country": "USD", "date": "2026-11-12T08:30:00-05:00", "impact": "High", "forecast": "0.3%", "previous": "0.4%"},
    {"title": "Non-Farm Employment Change", "country": "USD", "date": "2026-11-06T08:30:00-05:00", "impact": "High", "forecast": "119K", "previous": "22K"},
    {"title": "ADP Non-Farm Employment Change", "country": "USD", "date": "2026-11-04T08:15:00-05:00", "impact": "High", "forecast": "40K", "previous": "-32K"},
    {"title": "Bank Holiday", "country": "JPY", "date": "2026-11-23T00:00:00-05:00", "impact": "Holiday", "forecast": "", "previous": ""},
    {"title": "", "country": "USD", "date": "2026-11-12T08:30:00-05:00"},
]


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_USE_MOCK", "false")
    monkeypatch.setenv("CALENDAR_CONSENSUS_PATH", str(tmp_path / "cal.json"))
    web.reset_provider_status()
    return tmp_path / "cal.json"


def test_rows_parse_into_unverified_consensus_catalysts():
    now = datetime(2026, 11, 12, 10, tzinfo=UTC)
    rows = web.to_catalysts(web.parse_rows(SAMPLE), now=now)
    by = {r.title: r for r in rows}
    assert len(rows) == 4  # başlıksız satır atlandı
    cpi = by["CPI m/m"]
    assert cpi.source == "forexfactory_calendar" and cpi.verified is False
    assert cpi.region == "USD" and cpi.importance == "high"
    assert cpi.expected == 0.3 and cpi.previous == 0.4 and cpi.actual is None and cpi.unit == "percent"
    assert cpi.ts == datetime(2026, 11, 12, 13, 30, tzinfo=UTC)
    assert by["Non-Farm Employment Change"].expected == 119_000.0
    assert by["Bank Holiday"].importance == "low"


def test_fetch_is_cached_on_disk_and_reused_within_the_hour(live, monkeypatch):
    calls = []
    monkeypatch.setattr(web, "_fetch", lambda: calls.append(1) or SAMPLE)
    now = datetime(2026, 11, 12, 10, tzinfo=UTC)
    first = web.list_catalysts(now=now, past_days=30)
    second = web.list_catalysts(now=now, past_days=30)
    assert len(calls) == 1 and len(first) == len(second) == 4
    assert json.loads(live.read_text(encoding="utf-8"))["rows"]
    assert web.get_provider_status()["calendar_web"]["status"] == "ok"


def test_failed_fetch_keeps_stored_real_rows_and_marks_degraded(live, monkeypatch):
    monkeypatch.setattr(web, "_fetch", lambda: SAMPLE)
    now = datetime(2026, 11, 12, 10, tzinfo=UTC)
    web.list_catalysts(now=now, past_days=30)
    state = json.loads(live.read_text(encoding="utf-8"))
    state["fetched_at"] = "2026-01-01T00:00:00+00:00"  # bayat → yeniden çekim denenir
    live.write_text(json.dumps(state), encoding="utf-8")

    def boom():
        raise OSError("HTTP Error 429")

    monkeypatch.setattr(web, "_fetch", boom)
    rows = web.list_catalysts(now=now, past_days=30)
    assert len(rows) == 4
    st = web.get_provider_status()["calendar_web"]
    assert st["status"] == "degraded" and "429" in st["last_error"]


def test_calendar_list_window_keeps_one_past_day(live, monkeypatch):
    monkeypatch.setattr(web, "_fetch", lambda: SAMPLE)
    now = datetime(2026, 11, 12, 10, tzinfo=UTC)
    titles = {r.title for r in web.list_catalysts(now=now)}
    assert "CPI m/m" in titles and "Non-Farm Employment Change" not in titles  # 6 gün önce


def test_public_calendar_is_disabled_in_fixture_mode(monkeypatch) -> None:
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    web.reset_provider_status()
    assert web.list_catalysts() == []
    assert web.get_provider_status()["calendar_web"]["status"] == "disabled"


def test_nfp_spec_matches_new_title_but_not_adp():
    from packages.data.providers.macro import derived

    spec = next(s for s in derived.SPECS if s.key == "NFP")
    rows = {r.title: r for r in web.to_catalysts(web.parse_rows(SAMPLE), now=datetime(2026, 11, 12, tzinfo=UTC))}
    assert derived._matches(spec, rows["Non-Farm Employment Change"])
    assert not derived._matches(spec, rows["ADP Non-Farm Employment Change"])


def test_public_calendar_expectation_joins_official_release(live, monkeypatch):
    """Uçtan uca: ForexFactory başlıkları (CPI m/m, Core CPI m/m) resmî FRED satırına beklenti olarak eşleşir."""
    from types import SimpleNamespace

    from packages.data.providers.macro import derived
    from packages.data.providers.price import fred

    def months(values, start=(2025, 8)):
        year, month, out = start[0], start[1], []
        for value in values:
            out.append(SimpleNamespace(ts=datetime(year, month, 1, tzinfo=UTC), close=value))
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return out

    monkeypatch.setattr(fred, "get_series", lambda sid, start=None: months([100.0 + 0.3 * i for i in range(14)]))
    monkeypatch.setattr(web, "_fetch", lambda: [
        {"title": "CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High", "forecast": "0.2%", "previous": "0.4%"},
        {"title": "Core CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High", "forecast": "0.3%", "previous": "0.3%"},
    ])
    rows = {r.title: r for r in derived.releases(datetime(2026, 10, 15, tzinfo=UTC))}
    assert rows["US CPI (MoM)"].expected == 0.2
    assert rows["US Core CPI (MoM)"].expected == 0.3
    assert rows["US CPI (YoY)"].expected is None  # ölçüsü uyan beklenti yok
