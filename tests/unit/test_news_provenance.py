from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.data.providers.news.provenance import build_consensus, source_family, story_key
from packages.paper.news_setup import _event_context_for_symbol, is_live, view
from packages.paper.state import NewsPreparedSetup


def _headline(source: str, title: str, impact: dict[str, float]):
    return SimpleNamespace(
        id=f"{source}:{title}", source=source, title=title, title_tr=None,
        asset_impact=impact, verified=True, ts=datetime.now(UTC), url=None,
    )


def test_google_query_buckets_are_not_independent_publishers():
    assert source_family("World Wire") == "google_news:world_query"
    assert source_family("Gold Wire") == "google_news:metals_query"
    assert source_family("CNBC") == "direct:cnbc.com"
    assert source_family("US Foreign Affairs") == source_family("Iran Foreign Affairs")


def test_publisher_aliases_collapse_feed_labels_and_urls():
    assert source_family("Seeking Alpha") == source_family("https://seekingalpha.com/news/example")
    assert source_family("direct:seeking_alpha") == "direct:seekingalpha.com"
    assert source_family("Investing Emtia") == source_family("https://www.investing.com/news/commodities")
    assert source_family("CNBC") == source_family("https://www.cnbc.com/markets/")
    assert source_family("https://news.google.com/rss/articles/example") == "google_news:redirect"


def test_story_key_and_consensus_keep_conflicting_stories_visible():
    rows = [
        _headline("World Wire", "Oil supply disruption in Hormuz - AP News", {"BRENT": 1}),
        _headline("MarketWatch Top", "Oil prices fall as supply resumes", {"BRENT": -1}),
    ]
    report = build_consensus(rows)
    assert story_key("Tehran warns over Strait") == story_key("Iran threat over strait")
    asset = next(row for row in report["assets"] if row["symbol"] == "BRENT")
    assert asset["consensus"] == "MIXED"
    assert asset["evidence_status"] == "CONFLICT"
    assert report["proxy_headline_count"] == 1
    assert report["independent_source_families"] == 2


def test_expired_prepared_setup_is_not_reported_as_live():
    now = datetime.now(UTC)
    setup = NewsPreparedSetup(
        id="news::old", symbol="BRENT", timeframe="1h", side="long",
        created_at=(now - timedelta(hours=2)).isoformat(),
        valid_until=(now - timedelta(hours=1)).isoformat(), status="ARMED",
    )
    assert not is_live(setup, now)
    assert view(setup, now)["status"] == "EXPIRED"


def test_news_setup_requires_asset_bound_evidence():
    world = {"geopolitical_events": [{
        "event_id": "e1", "event_type": "SANCTIONS", "evidence": ["XRP wallet restrictions"],
    }]}
    assert _event_context_for_symbol(world, "BTCUSD") is None
