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
    assert len(rows) == 1 and rows[0]["group"] == "topic" and rows[0]["source"] == "Test Feed"
    assert rows[0]["v"] == first_seen.SCHEMA_VERSION


def test_first_parse_at_each_depth_is_boot(ledger) -> None:
    """Tick en yeni 6'yı, haber keşfi 15'i okur: keşfin ilk turunda görülen eski başlıklar 'yeni' sayılmaz."""
    top = [_h(f"n{i}") for i in range(6)]
    deep = top + [_h(f"o{i}") for i in range(9)]
    first_seen.record("u|6|1", top, group="geo", now=NOW)
    first_seen.record("u|15|0", deep, group="geo", now=NOW + timedelta(minutes=3))
    first_seen.record("u|6|1", [_h("fresh"), *top[:5]], group="geo", now=NOW + timedelta(minutes=4))
    rows = {r["id"]: r for r in _rows(ledger)}
    assert all(rows[f"o{i}"]["boot"] for i in range(9))
    assert rows["fresh"]["boot"] is False


def test_rss_tick_then_discovery_depth_does_not_fake_new_arrivals(ledger, monkeypatch) -> None:
    now = datetime.now(UTC)

    def xml(n_fresh: int) -> str:
        items = "".join(
            f"<item><title>Bitcoin story {i}</title><pubDate>"
            f"{(now - timedelta(minutes=10 * i + 30)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
            for i in range(15))
        fresh = "".join(
            f"<item><title>Bitcoin fresh {j}</title><pubDate>"
            f"{(now - timedelta(minutes=1)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
            for j in range(n_fresh))
        return f"<rss><channel>{fresh}{items}</channel></rss>"

    feed = ({"url": "https://example.test/depth", "source": "Depth Feed"},)
    body = {"x": xml(0)}
    monkeypatch.setattr(rss, "default_fetch", lambda url: body["x"])
    for depth in (6, 15):  # tick, sonra haber keşfi
        rss.reset_cache()
        rss.fetch_feed_group(feed, max_items=depth)
    body["x"] = xml(1)
    rss.reset_cache()
    rss.fetch_feed_group(feed, max_items=6)
    rows = _rows(ledger)
    assert len(rows) == 16
    assert [r["title"] for r in rows if not r["boot"]] == ["Bitcoin fresh 0"]


def test_group_comes_from_the_feed_list_not_the_caller(ledger, monkeypatch) -> None:
    pub = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = f"<rss><channel><item><title>Iran warns Israel over strikes</title><pubDate>{pub}</pubDate></item></channel></rss>"
    geo_feed = next(f for f in rss.GEO_FEEDS if f["source"] == "NYT World")
    monkeypatch.setattr(rss, "default_fetch", lambda url: xml)
    rss.reset_cache()
    rss.fetch_feed_group((geo_feed,), geo=False, max_items=15)  # haber keşfi yolu: süzgeçsiz
    assert _rows(ledger)[0]["group"] == "geo"


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
