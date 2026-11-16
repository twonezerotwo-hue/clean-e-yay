"""Seçim/İran haber etkisi ve gümüş ad koruması (2026-11-06).

Canlıda "Democrats win the presidential election" hiçbir varlığa, "Trump would
strike Iran again" yalnız VIX'e bağlanıyordu; "Nate Silver" / "Silver Bulletin"
ise gümüş ve altına düşüş etkisi yazıyordu. Taze haber yönü kapısı ölçümde
kârlı işlemleri durdurduğu için alınmadı (owner kararı); bu dosya yalnız
sınıflandırıcıyı sınar.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime

import pytest

from packages.data.providers.news import classify, rss
from packages.discovery import news_discovery as nd

# ------------------------------------------------------------------ sınıflandırıcı


@pytest.mark.parametrize("title", [
    "Democrats win the presidential election in a landslide",
    "Democrats win control of both chambers after midterm election results",
    "Trump loses election, concedes to Democrats",
])
def test_democratic_election_outcome_reaches_metals_dollar_and_rates(title):
    assert classify.classify_asset_impact(title, "neutral") == {
        "XAGUSD": 1.0, "XAUUSD": 1.0, "DXY": -1.0, "US10Y": -1.0,
    }


@pytest.mark.parametrize("title", [
    "Democrats lost the House in midterm elections",   # kaybeden Demokrat
    "Republicans sweep midterm elections",              # Cumhuriyetçi sonuç: yön uydurulmaz
    "Democrats win vote on spending bill",              # seçim değil
    "Nate Silver publishes election result forecast",   # kişi adı
])
def test_non_democratic_or_non_election_text_gets_no_macro_profile(title):
    impact = classify.classify_asset_impact(title, "neutral")
    assert "XAGUSD" not in impact and "US10Y" not in impact


@pytest.mark.parametrize("title", [
    "Trump says he would strike Iran again, has no regrets",
    "Trump says he has no regret about Iran war and would do it again after midterms",
])
def test_iran_repeat_statement_reaches_safe_haven_and_risk_premium(title):
    impact = classify.classify_asset_impact(title, "bearish")
    assert impact == {"XAGUSD": 1.0, "XAUUSD": 1.0, "VIX": 1.0, "BRENT": 1.0}


def test_iran_profile_keeps_risk_up_even_with_neutral_sentiment():
    impact = classify.classify_asset_impact(
        "Trump says he would strike Iran again, has no regrets", "neutral")
    assert impact["VIX"] == 1.0


def test_iran_ceasefire_is_not_escalation():
    impact = classify.classify_asset_impact(
        "Iran ceasefire holds after war; election impact fades", "neutral")
    assert "XAGUSD" not in impact and impact.get("VIX", 0.0) == 0.0


def test_silver_person_and_place_names_are_not_the_metal():
    for title in ("Nate Silver drops jaw-dropping stat on election result",
                  "Silver Rail will reopen after road repairs"):
        impact = classify.classify_asset_impact(title, "bearish")
        assert "XAGUSD" not in impact and "XAUUSD" not in impact, title


def test_silver_metal_and_ticker_still_map():
    assert classify.classify_asset_impact(
        "Gold and silver rise as weak payrolls cut Fed-hike odds", "bullish")["XAGUSD"] == 1.0
    assert classify.classify_asset_impact("SI=F rallies while the dollar slips", "bullish")["XAGUSD"] == 1.0
    assert classify.classify_asset_impact("Silver slips as dollar firms", "bearish")["XAGUSD"] == -1.0
    assert classify.classify_asset_impact("Gümüş fiyatları yükseldi", "bullish")["XAGUSD"] == 1.0


def test_silver_headline_no_longer_tags_gold():
    assert "XAUUSD" not in classify.classify_asset_impact("Silver rallies to two-week high", "bullish")


def test_rss_summary_binds_explicit_silver_ticker_only():
    pub = format_datetime(datetime.now(UTC))
    xml = f"""<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>Gold and bitcoin get a midterm pulse</title>
      <description>Tickers GC=F, DX-Y.NYB and SI=F are both rallying in early trading while the dollar slips.</description>
      <link>https://example.com/silver</link><pubDate>{pub}</pubDate>
    </item></channel></rss>"""
    impact = rss.parse_feed(xml, "TestFeed")[0].asset_impact
    assert impact.get("XAGUSD") == 1.0
    # Özetin geri kalanı ("dollar slips") eşlemeye girmez.
    assert "DXY" not in impact


def test_discovery_adds_explicit_silver_ticker_but_not_person():
    batch = [{
        "title": "Gold and bitcoin were weak; midterms gave them a pulse",
        "article": {"excerpt": "Tickers BTC-USD GC=F DX-Y.NYB SI=F are both rallying while dollar slips."},
    }]
    out = nd._augment_explicit_silver([{"h": 1, "c": "toparlanma", "a": []}], batch, max_assets=3)
    assert out[0]["a"] == [{
        "t": "SI=F", "n": "Silver futures", "d": "up", "k": "high",
        "m": "Gümüş fiyatı haber metninde doğrudan bağlandı",
    }]
    person = nd._augment_explicit_silver(
        [{"h": 1, "c": "yorum", "a": []}],
        [{"title": "Nate Silver drops a jaw-dropping election stat", "article": {"excerpt": ""}}],
        max_assets=3,
    )
    assert person[0]["a"] == []
