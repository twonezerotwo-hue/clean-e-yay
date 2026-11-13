"""Olay takvimi (config/event_calendar.yaml) veri korumaları.

Takvim elle tutulur; yanlış ya da eksik bir gün, olay riski kapısının yanlış
günde kapanması demektir (12 Kasım 2026: CPI 10 Kasım'da açıklandı, dosya 12
Kasım diyordu → gerçek gün korumasız geçti, ertesi 24 saat boşuna kapalı kaldı).
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import yaml

from packages.data.providers import calendar as calendar_provider
from packages.risk import event_risk


def _events() -> dict[str, dict]:
    raw = yaml.safe_load(calendar_provider.DEFAULT_CALENDAR_PATH.read_text(encoding="utf-8"))["events"]
    assert len({e["id"] for e in raw}) == len(raw), "takvimde yinelenen id var"
    return {e["id"]: e for e in raw}


def test_bls_releases_cover_every_month_without_gaps() -> None:
    """NFP/CPI/PPI her ay bir kez; id'deki ay yayın ayıdır. Eksik ay = korumasız gün."""
    ev = _events()
    last = max(date.fromisoformat(e["date"]) for k, e in ev.items() if k.startswith(("nfp_", "cpi_", "ppi_")))
    year, month = 2026, 6
    while (year, month) <= (last.year, last.month):
        for kind in ("nfp", "cpi", "ppi"):
            entry = ev.get(f"{kind}_{year}_{month:02d}")
            assert entry is not None, f"{kind} {year}-{month:02d} takvimde yok"
            released = date.fromisoformat(entry["date"])
            assert (released.year, released.month) == (year, month), entry
            assert released.weekday() < 5, f"{entry['id']} hafta sonuna denk geliyor"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def test_dates_corrected_against_official_calendars() -> None:
    """13 Kasım 2026'da bls.gov ve federalreserve.gov ile karşılaştırılan günler."""
    ev = _events()
    official = {
        "cpi_2026_10": "2026-10-14", "ppi_2026_10": "2026-10-15", "fomc_2026_10": "2026-10-28",
        "cpi_2026_11": "2026-11-10", "ppi_2026_11": "2026-11-13",
        "fomc_2026_12": "2026-12-09", "cpi_2026_12": "2026-12-10", "ppi_2026_12": "2026-12-15",
    }
    assert {k: ev[k]["date"] for k in official} == official


def test_gate_closes_before_the_real_cpi_release_not_two_days_later() -> None:
    def level(now: datetime) -> str:
        cats = calendar_provider.list_catalysts(
            limit=50, yaml_path=calendar_provider.DEFAULT_CALENDAR_PATH, reference=now
        )
        return event_risk.assess(cats, now=now).level

    # Ekim CPI: 10 Kasım 2026 08:30 ET = 13:30 UTC
    assert level(datetime(2026, 11, 10, 6, 0, tzinfo=UTC)) == "NO_POSITION_INCREASE"
    assert level(datetime(2026, 11, 12, 6, 0, tzinfo=UTC)) != "NO_POSITION_INCREASE"
