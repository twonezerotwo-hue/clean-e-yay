"""Dış kanıt katmanı (owner kararı 2026-10-30) — offline, sahte yanıtlarla.

- Ayrıştırıcılar gerçek yanıt biçimini okur (2026-10-30'da canlı doğrulandı).
- Kaynak kendi aralığında yenilenir; hata olursa son iyi veri bayat işaretlenir.
- Net likidite yalnız üç girdi de varsa hesaplanır; uç karara girmez etiketini taşır.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from packages.data.providers import evidence as ev

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_EVIDENCE_PATH", str(tmp_path / "external_evidence.json"))
    monkeypatch.setenv("FRED_API_KEY", "test-key")


def test_fred_series_latest_and_four_week_change():
    obs = [{"date": (date(2026, 10, 29) - timedelta(days=i)).isoformat(), "value": str(3.5 - i * 0.01)} for i in range(40)]
    obs.insert(1, {"date": "2026-10-28", "value": "."})  # FRED boş gün işareti
    out = ev.fetch_fred_series(lambda url: {"observations": obs})
    hy = out["BAMLH0A0HYM2"]
    assert hy["date"] == "2026-10-29" and hy["value"] == 3.5
    assert hy["change_4w"] == pytest.approx(0.28, abs=1e-6)


def test_fred_calendar_keeps_major_releases_only():
    rows = [
        {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-11-12"},
        {"release_id": 279, "release_name": "Economic Policy Uncertainty", "date": "2026-10-30"},
        {"release_id": 101, "release_name": "FOMC Press Release", "date": "2026-10-30"},
        {"release_id": 101, "release_name": "FOMC Press Release", "date": "2026-10-30"},
    ]
    out = ev.fetch_fred_calendar(lambda url: {"release_dates": rows}, today=date(2026, 10, 30))
    assert [r["release"] for r in out] == ["Consumer Price Index", "FOMC Press Release"]


def test_treasury_tga_closing_balance_and_weekly_change():
    data = []
    for i in range(10):
        d = (date(2026, 10, 28) - timedelta(days=i)).isoformat()
        data.append({"record_date": d, "account_type": "Treasury General Account (TGA) Opening Balance", "open_today_bal": "1"})
        data.append({"record_date": d, "account_type": "Treasury General Account (TGA) Closing Balance",
                     "open_today_bal": str(1_000_000 + i * 1000)})
    out = ev.fetch_treasury_tga(lambda url: {"data": data})
    assert out["date"] == "2026-10-28" and out["tga_musd"] == 1_000_000.0
    assert out["change_1w_musd"] == -7000.0


def test_cftc_net_noncommercial_positioning():
    rows = [
        {"cftc_contract_market_code": "088691", "market_and_exchange_names": "GOLD - COMEX",
         "report_date_as_yyyy_mm_dd": "2026-10-20T00:00:00.000", "noncomm_positions_long_all": "237142",
         "noncomm_positions_short_all": "37277", "open_interest_all": "402279"},
        {"cftc_contract_market_code": "088691", "report_date_as_yyyy_mm_dd": "2026-10-13T00:00:00.000",
         "noncomm_positions_long_all": "240000", "noncomm_positions_short_all": "32121", "open_interest_all": "400000"},
    ]
    gold = ev.fetch_cftc_cot(lambda url: rows)["XAUUSD"]
    assert gold["noncomm_net"] == 199865.0 and gold["report_date"] == "2026-10-20"
    assert gold["noncomm_net_pct_oi"] == pytest.approx(49.68, abs=0.01)
    assert gold["change_1w"] == -8014.0


def test_gdelt_empty_response_is_an_error_not_a_value():
    with pytest.raises(RuntimeError):
        ev.fetch_gdelt_tone(lambda url: {}, sleep=lambda s: None)


def test_fear_greed_latest_and_week_average():
    rows = [{"value": str(v), "value_classification": "Fear", "timestamp": "1793318400"} for v in (30, 51, 60, 40, 50, 45, 59, 70)]
    out = ev.fetch_fear_greed(lambda url: {"data": rows})
    assert out["value"] == 30.0 and out["classification"] == "Fear" and out["avg_7d"] == 47.9


def test_refresh_respects_ttl_and_keeps_stale_data_on_error():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return {"value": 1}

    first = ev.refresh(now=NOW, fetchers={"fear_greed": ok})
    assert first["sources"]["fear_greed"]["status"] == "ok" and calls["n"] == 1
    ev.refresh(now=NOW + timedelta(hours=1), fetchers={"fear_greed": ok})  # 6 sa aralık dolmadı
    assert calls["n"] == 1

    def boom():
        raise OSError("ağ")

    later = ev.refresh(now=NOW + timedelta(hours=7), fetchers={"fear_greed": boom})
    row = later["sources"]["fear_greed"]
    assert row["status"] == "error" and row["stale"] is True and row["data"] == {"value": 1}


def test_net_liquidity_needs_all_inputs():
    sources = {
        "fred_series": {"data": {"WALCL": {"value": 6_600_000.0, "date": "2026-10-29"},
                                 "RRPONTSYD": {"value": 50.0, "date": "2026-10-29"}}},
        "treasury_tga": {"data": {"tga_musd": 1_000_000.0, "date": "2026-10-28"}},
    }
    assert ev._net_liquidity(sources)["value_musd"] == 5_550_000.0
    sources["treasury_tga"]["data"] = {}
    assert ev._net_liquidity(sources) is None


def test_endpoint_serves_artifact_as_evidence_only():
    from apps.api.main import app

    ev.refresh(now=NOW, fetchers={"fear_greed": lambda: {"value": 30.0}})
    body = TestClient(app).get("/api/v1/data/external-evidence").json()
    assert body["available"] is True and body["decision_usage"] == "evidence_only"
    assert body["sources"]["fear_greed"]["data"] == {"value": 30.0}
