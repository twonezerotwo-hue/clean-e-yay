from datetime import UTC, datetime
from types import SimpleNamespace

from apps.api.routers import regime_report


def test_news_wall_is_read_only_and_preserves_multi_country_context(monkeypatch):
    headline = SimpleNamespace(
        id="h1",
        source="US Foreign Affairs",
        region="USA",
        title="Trump warns Iran after China and Russia statements",
        title_tr=None,
        sentiment="bearish",
        sentiment_v2="bearish",
        asset_impact={"BRENT": 1.0},
        url="https://example.test/story",
        freshness="FRESH",
        ts=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(regime_report, "list_headlines", lambda limit: [headline])
    monkeypatch.setattr(regime_report, "get_provider_status", lambda: {"news": {"status": "ok"}})

    result = regime_report.get_news_current(200)

    assert result["count"] == 1
    assert result["paper_safe"] is True
    assert result["no_execution"] is True
    assert result["headlines"][0]["countries"] == ["USA", "Iran", "China", "Russia"]
    assert result["coverage"]["requested_limit"] == 96
