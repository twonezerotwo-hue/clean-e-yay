from __future__ import annotations

from datetime import UTC, datetime


def test_public_calendar_parser_extracts_shadow_fields() -> None:
    from packages.data.providers.calendar.web import parse_events

    body = '"calendarEventsByDate":{"2026-10-29":[{"occurrenceId":42,"date":"2026-10-29","time":"2026-10-29T12:30:00Z","event":"Consumer Price Index","country":"United States","currencyFlag":"US","importance":"3","actual":"3.1%","forecast":"3.0%","previous":"2.9%"}]}'
    now = datetime(2026, 10, 29, 10, tzinfo=UTC)
    rows = parse_events(body, now=now)

    assert len(rows) == 1
    row = rows[0]
    assert row.source == "investing_web_calendar"
    assert row.verified is False
    assert row.region == "United States"
    assert row.importance == "high"
    assert row.actual == 3.1
    assert row.expected == 3.0
    assert row.previous == 2.9
    assert row.ts == datetime(2026, 10, 29, 12, 30, tzinfo=UTC)


def test_public_calendar_is_disabled_in_fixture_mode(monkeypatch) -> None:
    from packages.data.providers.calendar import web

    monkeypatch.setenv("TEST_USE_MOCK", "true")
    web.reset_provider_status()
    assert web.list_catalysts() == []
    assert web.get_provider_status()["calendar_web"]["status"] == "disabled"
