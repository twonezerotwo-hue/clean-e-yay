from datetime import UTC, datetime

from packages.data.providers import macro


def test_bls_parser_maps_actual_and_previous_without_network(monkeypatch):
    payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{
            "seriesID": "CUUR0000SA0",
            "data": [
                {"year": "2026", "period": "M09", "value": "324.800"},
                {"year": "2026", "period": "M08", "value": "323.900"},
            ],
        }]},
    }
    monkeypatch.setattr(macro, "_json_request", lambda *args, **kwargs: payload)
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    rows = macro._bls_releases(datetime(2026, 10, 29, tzinfo=UTC))
    assert len(rows) == 1
    assert rows[0].actual == 324.8
    assert rows[0].previous == 323.9
    assert rows[0].verified is True
    assert rows[0].source == "bls_official"


def test_bls_parser_accepts_quarterly_jolts_and_eci(monkeypatch):
    payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [
            {"seriesID": "JTS000000000000000JOL", "data": [
                {"year": "2026", "period": "M08", "value": "7227"},
                {"year": "2026", "period": "M07", "value": "7212"},
            ]},
            {"seriesID": "CIU2020000000000A", "data": [
                {"year": "2026", "period": "Q03", "value": "3.1"},
                {"year": "2026", "period": "Q02", "value": "3.0"},
            ]},
        ]},
    }
    monkeypatch.setattr(macro, "_json_request", lambda *args, **kwargs: payload)
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    rows = macro._bls_releases(datetime(2026, 10, 29, tzinfo=UTC))
    by_title = {row.title: row for row in rows}
    assert by_title["US Job Openings"].actual == 7227.0
    assert by_title["US Job Openings"].unit == "thousands"
    assert by_title["US Employment Cost Index"].actual == 3.1
    assert by_title["US Employment Cost Index"].previous == 3.0
    assert by_title["US Employment Cost Index"].ts.month == 7


def test_official_provider_is_disabled_in_fixture_mode(monkeypatch):
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    macro.reset_provider_status()
    assert macro.list_releases() == []
    assert macro.get_provider_status()["macro_bls"]["status"] == "disabled"


def test_eia_parser_uses_v2_series_facet(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    captured = {}
    def _fake(url, **kwargs):
        captured["url"] = url
        if "natural-gas" in url:
            return {"response": {"data": [
                {"period": "2026-10-23", "value": "3869"},
                {"period": "2026-10-16", "value": "3845"},
            ]}}
        return {"response": {"data": [
            {"period": "2026-10-23", "value": "410625"},
            {"period": "2026-10-16", "value": "412517"},
        ]}}
    monkeypatch.setattr(macro, "_json_request", _fake)
    rows = macro._eia_releases(datetime(2026, 10, 29, tzinfo=UTC))
    crude = next(row for row in rows if row.title == "US Crude Oil Inventories")
    gas = next(row for row in rows if row.title == "US Natural Gas Storage")
    assert crude.actual == 410625.0
    assert crude.previous == 412517.0
    assert gas.actual == 3869.0
    assert gas.unit == "billion_cubic_feet"
    assert "facets%5Bseries%5D%5B%5D=NW2_EPG0_SWO_R48_BCF" in captured["url"]
