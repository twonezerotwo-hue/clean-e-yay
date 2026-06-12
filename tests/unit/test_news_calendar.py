"""P0 — News / geo / calendar provider birim testleri.

Hepsi offline (live network YOK):
- RSS fixture XML parse (fetch_fn enjekte; urlopen patch'li bekçi).
- Geo başlık bölge sınıflandırması.
- Asset-impact yön çıkarımı.
- YAML calendar load + bozuk/eksik dosya → DEGRADED + boş liste (mock yok).
- High-impact yakın takvim olayı → event riski WATCH/NO_POSITION_INCREASE.
"""
from __future__ import annotations

import urllib.request
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from packages.data.providers import calendar as cal_provider
from packages.data.providers.news import classify, rss
from packages.risk import event_risk


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Hiçbir test live network'e çıkmamalı."""
    def _boom(*_a, **_k):  # pragma: no cover
        raise AssertionError("news/calendar testi live network'e çıkmamalı")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)


def _rss(items: list[tuple[str, datetime]]) -> str:
    rows = "".join(
        f"<item><title>{t}</title><link>https://x/{i}</link>"
        f"<pubDate>{format_datetime(d)}</pubDate></item>"
        for i, (t, d) in enumerate(items)
    )
    return f"<?xml version='1.0'?><rss><channel>{rows}</channel></rss>"


# ---------------- RSS parse ----------------

def test_parse_feed_extracts_fresh_headline() -> None:
    now = datetime.now(UTC)
    xml = _rss([("Bitcoin rally extends as ETF inflows surge", now - timedelta(hours=1))])
    out = rss.parse_feed(xml, "CoinDesk", now=now)
    assert len(out) == 1
    h = out[0]
    assert h.verified is True
    assert h.source == "CoinDesk"
    assert h.sentiment == "bullish"
    assert h.freshness == "FRESH"
    assert "BTCUSD" in h.asset_impact


def test_parse_feed_drops_stale_and_dateless() -> None:
    now = datetime.now(UTC)
    xml = _rss(
        [
            ("Old gold news", now - timedelta(hours=48)),   # > 24h → atılır
            ("Fresh oil spike", now - timedelta(minutes=30)),
        ]
    )
    out = rss.parse_feed(xml, "MarketWatch", now=now)
    titles = [h.title for h in out]
    assert "Fresh oil spike" in titles
    assert "Old gold news" not in titles


def test_parse_feed_drops_irrelevant() -> None:
    now = datetime.now(UTC)
    xml = _rss([("Celebrity wedding recipe horoscope", now - timedelta(minutes=10))])
    assert rss.parse_feed(xml, "X", now=now) == []


def test_geo_feed_requires_region() -> None:
    now = datetime.now(UTC)
    xml = _rss(
        [
            ("Iran missile strike escalates tension", now - timedelta(minutes=20)),
            ("Generic market chatter today", now - timedelta(minutes=20)),
        ]
    )
    out = rss.parse_feed(xml, "World Wire", geo=True, now=now)
    titles = [h.title for h in out]
    assert any("Iran" in t for t in titles)
    assert "Generic market chatter today" not in titles


def test_fetch_feed_group_uses_injected_fetch() -> None:
    now = datetime.now(UTC)
    xml = _rss([("Fed signals rate cut, risk-on", now - timedelta(minutes=15))])
    headlines, ok, err = rss.fetch_feed_group(
        ({"url": "u", "source": "CNBC"},), fetch_fn=lambda _u: xml
    )
    assert ok == 1 and err is None
    assert headlines and headlines[0].source == "CNBC"


def test_fetch_feed_group_swallows_errors() -> None:
    def _raise(_u: str) -> str:
        raise RuntimeError("boom")

    headlines, ok, err = rss.fetch_feed_group(
        ({"url": "u", "source": "BadFeed"},), fetch_fn=_raise
    )
    assert headlines == [] and ok == 0
    assert err is not None and "BadFeed" in err


# ---------------- classify ----------------

@pytest.mark.parametrize(
    "title, region",
    [
        ("Tehran warns over strait of hormuz", "Iran"),
        ("Netanyahu addresses Gaza operation", "Israel"),
        ("PBOC holds yuan as Beijing eyes Taiwan", "China"),
        ("Kremlin comments on Ukraine front", "Russia"),
        ("ECB's Lagarde speaks in Brussels", "Europe"),
        ("White House and Congress debate budget", "USA"),
    ],
)
def test_detect_region(title: str, region: str) -> None:
    assert classify.detect_region(title) == region


def test_detect_region_none_for_local() -> None:
    assert classify.detect_region("Quarterly earnings beat estimates") is None


def test_asset_impact_directions() -> None:
    bull = classify.classify_asset_impact("Gold surges to record", "bullish")
    assert bull.get("XAUUSD") == 1.0
    # Orta Doğu eskalasyonu → enerji risk primi (sentiment'ten bağımsız)
    war = classify.classify_asset_impact("Israel airstrike near Gaza", "bearish")
    assert war.get("BRENT") == 1.0


# ---------------- calendar YAML load ----------------

def _write_cal(tmp_path, body: str):
    p = tmp_path / "cal.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_calendar_loads_upcoming_event(tmp_path) -> None:
    cal_provider.reset_provider_status()
    ref = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
    p = _write_cal(
        tmp_path,
        'events:\n'
        '  - id: "cpi_test"\n'
        '    date: "2026-06-12"\n'
        '    name: "ABD CPI"\n'
        '    importance: "CRITICAL"\n',
    )
    cats = cal_provider.list_catalysts(yaml_path=p, reference=ref)
    assert len(cats) == 1
    assert cats[0].importance == "critical"
    assert cats[0].verified is True
    assert cal_provider.get_provider_status()["calendar"]["status"] == "ok"


def test_calendar_filters_past_events(tmp_path) -> None:
    ref = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)
    p = _write_cal(
        tmp_path,
        'events:\n'
        '  - id: "past"\n'
        '    date: "2026-06-01"\n'
        '    name: "Old NFP"\n'
        '    importance: "HIGH"\n',
    )
    assert cal_provider.list_catalysts(yaml_path=p, reference=ref) == []


def test_calendar_corrupt_file_degraded_no_mock(tmp_path) -> None:
    cal_provider.reset_provider_status()
    p = _write_cal(tmp_path, "events: : : not valid yaml [")
    cats = cal_provider.list_catalysts(yaml_path=p)
    assert cats == []  # mock üretilmez
    assert cal_provider.get_provider_status()["calendar"]["status"] == "degraded"


# ---------------- calendar → event riski köprüsü ----------------

def test_high_impact_calendar_event_triggers_event_risk(tmp_path) -> None:
    # Olay referans anından ~2 saat sonra (12:00 UTC kabul) → block penceresinde.
    ref = datetime(2026, 6, 12, 10, 0, tzinfo=UTC)
    p = _write_cal(
        tmp_path,
        'events:\n'
        '  - id: "fomc_test"\n'
        '    date: "2026-06-12"\n'
        '    name: "FOMC Karar"\n'
        '    importance: "CRITICAL"\n',
    )
    cats = cal_provider.list_catalysts(yaml_path=p, reference=ref)
    res = event_risk.assess(cats, now=ref)
    assert res.level == "NO_POSITION_INCREASE"
    assert res.restrictive is True


def test_low_impact_calendar_event_no_block(tmp_path) -> None:
    ref = datetime(2026, 6, 12, 10, 0, tzinfo=UTC)
    p = _write_cal(
        tmp_path,
        'events:\n'
        '  - id: "claims_test"\n'
        '    date: "2026-06-12"\n'
        '    name: "Jobless Claims"\n'
        '    importance: "LOW"\n',
    )
    cats = cal_provider.list_catalysts(yaml_path=p, reference=ref)
    assert event_risk.assess(cats, now=ref).level == "NONE"
