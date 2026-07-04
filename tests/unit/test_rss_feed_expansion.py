"""RSS genişletme (2026-07-04, owner kararı — N1/kat 4) yapısal bekçileri.

Feed listesi koddan gelen veri-konfigürasyonudur; bu testler ağa ÇIKMAZ
(DATA_POLICY: canlı feed doğrulaması ekleme günü ayrıca yapıldı). Burada
korunan invariantlar: iyi-biçimli https URL, benzersiz url/source, ve
genişlemenin mevcut ayrıştırma davranışını değiştirmediği.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.data.providers.news import rss


def test_feed_definitions_wellformed_and_unique():
    all_feeds = rss.MARKET_FEEDS + rss.GEO_FEEDS
    urls = [f["url"] for f in all_feeds]
    sources = [f["source"] for f in all_feeds]
    assert all(u.startswith("https://") for u in urls)
    assert all(s.strip() for s in sources)
    assert len(set(urls)) == len(urls), "çift URL feed listesinde"
    assert len(set(sources)) == len(sources), "çift source adı"


def test_expansion_feeds_present():
    # 2026-07-04 genişlemesi: eklenen kaynaklar listede (yanlışlıkla silinme
    # regresyonuna karşı) — sayı sabitlenmez, gelecek eklemeler test kırmasın.
    market_sources = {f["source"] for f in rss.MARKET_FEEDS}
    geo_sources = {f["source"] for f in rss.GEO_FEEDS}
    assert {
        "The Block",
        "CryptoSlate",
        "Bitcoin.com",
        "Yahoo Finance",
        "MarketWatch Top",
        "Gold Wire",
    } <= market_sources
    assert {"Guardian World", "France24"} <= geo_sources


def test_parse_feed_behavior_unchanged_by_expansion():
    # Genişleme yalnız feed LİSTESİNİ büyütür; ayrıştırma birebir aynı —
    # taze item sayılır, 24h+ eskisi atılır, MAX_PER_FEED tavanı korunur.
    now = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    fresh = (now - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    stale = (now - timedelta(hours=30)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(
        f"<item><title>Bitcoin rallies to new high {i}</title>"
        f"<pubDate>{fresh if i < 8 else stale}</pubDate></item>"
        for i in range(10)
    )
    xml_text = f"<rss><channel>{items}</channel></rss>"
    heads = rss.parse_feed(xml_text, "The Block", now=now)
    assert len(heads) == rss.MAX_PER_FEED  # 8 taze → tavan 6
    assert all(h.verified for h in heads)
    assert all(h.source == "The Block" for h in heads)
