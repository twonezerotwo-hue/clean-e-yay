"""Haber ilk-görülme kaydı ve 13 Kasım 2026 doğrudan akış değişikliği."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from packages.data.providers.news import first_seen, rss
from packages.data.providers.news.provenance import source_family

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "first_seen.jsonl"
    monkeypatch.setenv("NEWS_FIRST_SEEN_PATH", str(path))
    first_seen.reset()
    yield path
    first_seen.reset()


def _h(hid: str, title: str = "Iran warns US over Hormuz", source: str = "NYT World") -> SimpleNamespace:
    return SimpleNamespace(id=hid, title=title, source=source, ts=NOW - timedelta(minutes=7),
                           url="https://www.nytimes.com/2026/11/13/world/x.html", region="Iran")


def _rows(path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_records_each_headline_once_and_marks_the_first_parse_as_boot(ledger) -> None:
    assert first_seen.record("u1", [_h("a"), _h("b")], group="geo", now=NOW) == 2
    assert first_seen.record("u1", [_h("a"), _h("c")], group="geo", now=NOW + timedelta(minutes=2)) == 1
    rows = _rows(ledger)
    assert [(r["id"], r["boot"]) for r in rows] == [("a", True), ("b", True), ("c", False)]
    c = rows[2]
    assert c["first_seen"] == (NOW + timedelta(minutes=2)).isoformat() and c["ts"] == (NOW - timedelta(minutes=7)).isoformat()
    assert c["family"] == "direct:nytimes.com" and c["proxy"] is False and c["group"] == "geo"
    assert c["story"]  # hikâye anahtarı kaynaklar arası eşleştirme için


def test_restart_does_not_duplicate_known_headlines(ledger) -> None:
    first_seen.record("u1", [_h("a")], group="geo", now=NOW)
    first_seen.reset()  # yeni süreç
    assert first_seen.record("u1", [_h("a"), _h("d")], group="geo", now=NOW + timedelta(hours=1)) == 1
    rows = _rows(ledger)
    assert [r["id"] for r in rows] == ["a", "d"]
    assert rows[1]["boot"] is True  # yeni süreçte bu akışın ilk ayrıştırması


def test_google_news_rows_are_marked_proxy(ledger) -> None:
    gn = SimpleNamespace(id="g", title="Iran threatens unlimited response - Al Jazeera", source="Iran Foreign Affairs",
                         ts=NOW, url="https://news.google.com/rss/articles/x", region="Iran")
    first_seen.record("gn", [gn], group="geo", now=NOW)
    row = _rows(ledger)[0]
    assert row["proxy"] is True and row["family"] == "google_news:foreign_affairs_query"


def test_record_never_raises(ledger, monkeypatch) -> None:
    monkeypatch.setenv("NEWS_FIRST_SEEN_PATH", str(ledger.parent / "missing_dir" / "x" / "f.jsonl"))
    first_seen.reset()
    bad = SimpleNamespace(id="z", title=None, source=None, ts="not-a-date", url=None, region=None)
    assert first_seen.record("u", [bad], group="market", now=NOW) in (0, 1)


def test_default_fetch_path_records_but_injected_fetch_does_not(ledger, monkeypatch) -> None:
    pub = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = f"<rss><channel><item><title>Bitcoin rallies</title><pubDate>{pub}</pubDate></item></channel></rss>"
    feeds = ({"url": "https://example.test/feed", "source": "Test Feed"},)
    rss.fetch_feed_group(feeds, fetch_fn=lambda url: xml)
    assert not ledger.exists()  # enjekte edilen getirme (testler) kayda yazmaz
    rss.reset_cache()
    monkeypatch.setattr(rss, "default_fetch", lambda url: xml)
    rss.fetch_feed_group(feeds)
    rows = _rows(ledger)
    assert len(rows) == 1 and rows[0]["group"] == "market" and rows[0]["source"] == "Test Feed"


def test_bloomberg_ft_come_from_publisher_feeds_not_google_news() -> None:
    feeds = rss.MARKET_FEEDS + rss.GEO_FEEDS
    sources = {f["source"] for f in feeds}
    assert {"Bloomberg Markets", "Bloomberg Politics", "FT World", "CNBC World", "NYT World"} <= sources
    assert "Bloomberg/FT" not in sources  # GN kopyası aynı haberi ikinci "bağımsız" aile gibi saydırırdı
    assert not any("bloomberg" in f["url"].casefold() and "news.google.com" in f["url"] for f in feeds)
    assert {f["source"] for f in rss.GEO_FEEDS} >= {"Bloomberg Politics", "FT World", "CNBC World", "NYT World"}
    # Aynı yayıncının iki akışı tek aile sayılır (bağımsız teyit şişmez)
    assert source_family("Bloomberg Markets") == source_family("Bloomberg Politics") == "direct:bloomberg.com"
    assert source_family("CNBC World") == source_family("CNBC") == "direct:cnbc.com"
    assert source_family("FT World", url="https://www.ft.com/content/abc") == "direct:ft.com"
