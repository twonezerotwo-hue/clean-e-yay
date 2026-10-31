"""Haber duygu sınıflandırıcısı (çekim-eki normalizasyonu) testleri.

- Çekimli haller yakalanır ("rebounds"/"surges"/"plunges"/"escalates");
  kök halinde geçenler, TR kelimeler ve gerçekten nötr başlıklar değişmez.
- RSS parse: başlığın sentiment'i ve asset_impact yönü aynı sınıflandırıcıdan.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime

from packages.data.providers.news import classify, rss

# 2026-07-02 canlı denetiminde yakalanan gerçek başlıklar (kanıt seti).
_REBOUNDS = "Bitcoin rebounds above $60k ahead of key US jobs data"


# --------------------------------- davranış ----------------------------------

def test_catches_english_inflections() -> None:
    assert classify.classify_sentiment(_REBOUNDS) == "bullish"
    assert classify.classify_sentiment("Bitcoin surges to new high") == "bullish"
    assert classify.classify_sentiment("Gold rallies as dollar weakens") == "bullish"
    assert classify.classify_sentiment("Stocks rallied after CPI print") == "bullish"
    assert classify.classify_sentiment("Bitcoin plunges 10% overnight") == "bearish"
    assert classify.classify_sentiment("Oil prices tumbled on demand fears") == "bearish"
    assert classify.classify_sentiment("Stocks falling on recession fears") == "bearish"
    # "growth" sözlükte bullish → falling(bearish) ile berabere = neutral
    assert classify.classify_sentiment("Yields falling as growth slows") == "neutral"


def test_stem_prefix_entries_now_work() -> None:
    """Sözlükteki 'escalat' kök girdisi prefix olarak eşleşir."""
    assert classify.classify_sentiment("Russia escalates attacks") == "bearish"
    assert classify.classify_sentiment("Tehran retaliates after strikes") == "bearish"


def test_short_words_not_prefix_matched() -> None:
    """<6 harf sözlük kelimeleri prefix sayılmaz: 'cut' → 'cutting-edge' tetiklemez."""
    assert classify.classify_sentiment("Cutting-edge chip factory opens") == "neutral"


def test_neutral_and_turkish_unchanged() -> None:
    assert classify.classify_sentiment("Here's what happened in crypto today") == "neutral"
    # TR kelimeler listede çekimli halleriyle var
    assert classify.classify_sentiment("Altın fiyatları yükseldi") == "bullish"


def test_tie_stays_neutral() -> None:
    """Oylama: eşitlik → neutral."""
    assert classify.classify_sentiment("Stocks gain as bonds fall") == "neutral"


# ------------------------------ RSS entegrasyonu -----------------------------

def _rss_xml(title: str) -> str:
    pub = format_datetime(datetime.now(UTC))
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>{title}</title><link>https://example.com/a</link>
  <pubDate>{pub}</pubDate></item>
</channel></rss>"""


def test_rss_headline_sentiment() -> None:
    heads = rss.parse_feed(_rss_xml(_REBOUNDS), "TestFeed")
    assert len(heads) == 1
    h = heads[0]
    # çekim eki indirgenir: rebounds → bullish
    assert h.sentiment == "bullish"
    assert h.verified is True


def test_rss_asset_impact_follows_sentiment() -> None:
    """asset_impact yönü başlığın sentiment'inden türer (BTC +1)."""
    heads = rss.parse_feed(_rss_xml(_REBOUNDS), "TestFeed")
    assert heads[0].sentiment == "bullish"
    assert heads[0].asset_impact.get("BTCUSD") == 1.0
