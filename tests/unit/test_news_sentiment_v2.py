"""M1 — news sentiment v2 (çekim-eki normalizasyonu) testleri.

- v1 REGRESYON: flag kapalıyken davranış bayt-aynı (çekimli kelimeler v1'de
  hâlâ kaçar — bu bilinçli: v1'e dokunulmadı, düzeltme v2'de).
- v2: çekimli haller yakalanır ("rebounds"/"surges"/"plunges"/"escalates");
  kök halinde geçenler, TR kelimeler ve gerçekten nötr başlıklar değişmez.
- Flag dispatch: default KAPALI → active=v1; threshold_override ile açık → v2.
- RSS parse: headline aktif sentiment'i + sentiment_v2 gözlemini birlikte taşır.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime

from packages.data.providers.news import classify, rss
from packages.data.registry.loader import threshold_override

# 2026-07-02 canlı denetiminde yakalanan gerçek başlıklar (kanıt seti).
_REBOUNDS = "Bitcoin rebounds above $60k ahead of key US jobs data"


# ------------------------------- v1 regresyon --------------------------------

def test_v1_still_misses_inflections() -> None:
    """v1'e DOKUNULMADI: çekimli haller v1'de hâlâ neutral (bayt-aynı garanti)."""
    assert classify.classify_sentiment(_REBOUNDS) == "neutral"
    assert classify.classify_sentiment("Bitcoin surges to new high") == "neutral"
    assert classify.classify_sentiment("Bitcoin plunges 10% overnight") == "neutral"
    # kök hali v1'de zaten çalışıyordu — çalışmaya devam eder
    assert classify.classify_sentiment("Bitcoin rebound above $60k") == "bullish"
    assert classify.classify_sentiment("Bitcoin plunge 10% overnight") == "bearish"


# --------------------------------- v2 davranış -------------------------------

def test_v2_catches_english_inflections() -> None:
    assert classify.classify_sentiment_v2(_REBOUNDS) == "bullish"
    assert classify.classify_sentiment_v2("Bitcoin surges to new high") == "bullish"
    assert classify.classify_sentiment_v2("Gold rallies as dollar weakens") == "bullish"
    assert classify.classify_sentiment_v2("Stocks rallied after CPI print") == "bullish"
    assert classify.classify_sentiment_v2("Bitcoin plunges 10% overnight") == "bearish"
    assert classify.classify_sentiment_v2("Oil prices tumbled on demand fears") == "bearish"
    assert classify.classify_sentiment_v2("Stocks falling on recession fears") == "bearish"
    # "growth" sözlükte bullish → falling(bearish) ile berabere = neutral (oylama v1 ile aynı)
    assert classify.classify_sentiment_v2("Yields falling as growth slows") == "neutral"


def test_v2_stem_prefix_entries_now_work() -> None:
    """Sözlükteki 'escalat' kök girdisi v1'de HİÇ eşleşemiyordu; v2 prefix'le yakalar."""
    assert classify.classify_sentiment("Russia escalates attacks") == "neutral"  # v1 kör
    assert classify.classify_sentiment_v2("Russia escalates attacks") == "bearish"
    assert classify.classify_sentiment_v2("Tehran retaliates after strikes") == "bearish"


def test_v2_short_words_not_prefix_matched() -> None:
    """<6 harf sözlük kelimeleri prefix sayılmaz: 'cut' → 'cutting-edge' tetiklemez."""
    assert classify.classify_sentiment_v2("Cutting-edge chip factory opens") == "neutral"


def test_v2_neutral_and_turkish_unchanged() -> None:
    assert classify.classify_sentiment_v2("Here's what happened in crypto today") == "neutral"
    # TR kelimeler listede çekimli halleriyle var — v1 ve v2 aynı okur
    assert classify.classify_sentiment("Altın fiyatları yükseldi") == "bullish"
    assert classify.classify_sentiment_v2("Altın fiyatları yükseldi") == "bullish"


def test_v2_tie_stays_neutral() -> None:
    """Oylama kuralı v1 ile aynı: eşitlik → neutral."""
    assert classify.classify_sentiment_v2("Stocks gain as bonds fall") == "neutral"


# ------------------------------- flag dispatch -------------------------------

def test_active_defaults_to_v1() -> None:
    """Config default'u false → aktif sınıflandırıcı v1 (davranış bayt-aynı)."""
    assert classify.sentiment_v2_enabled() is False
    assert classify.classify_sentiment_active(_REBOUNDS) == "neutral"


def test_active_switches_with_flag() -> None:
    with threshold_override({"news": {"sentiment_v2": True}}):
        assert classify.sentiment_v2_enabled() is True
        assert classify.classify_sentiment_active(_REBOUNDS) == "bullish"
    # scope dışında eski davranış geri gelir
    assert classify.classify_sentiment_active(_REBOUNDS) == "neutral"


# ------------------------------ RSS entegrasyonu -----------------------------

def _rss_xml(title: str) -> str:
    pub = format_datetime(datetime.now(UTC))
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>{title}</title><link>https://example.com/a</link>
  <pubDate>{pub}</pubDate></item>
</channel></rss>"""


def test_rss_headline_carries_active_and_v2() -> None:
    heads = rss.parse_feed(_rss_xml(_REBOUNDS), "TestFeed")
    assert len(heads) == 1
    h = heads[0]
    # flag default KAPALI: karar zincirinin gördüğü sentiment v1 (neutral)…
    assert h.sentiment == "neutral"
    # …v2 okuması gözlem alanında (aktivasyon kanıtı burada birikir)
    assert h.sentiment_v2 == "bullish"
    assert h.verified is True


def test_rss_asset_impact_follows_active_sentiment() -> None:
    """Flag açıkken asset_impact yönü de v2 sentiment'ten türer (BTC +1)."""
    with threshold_override({"news": {"sentiment_v2": True}}):
        heads = rss.parse_feed(_rss_xml(_REBOUNDS), "TestFeed")
    assert heads[0].sentiment == "bullish"
    assert heads[0].asset_impact.get("BTCUSD") == 1.0
