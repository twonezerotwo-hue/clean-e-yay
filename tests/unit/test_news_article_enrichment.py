from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from packages.data.providers.news import article_enrichment as ae

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def _headline(url: str | None = "https://news.example.test/story"):
    return SimpleNamespace(id="h1", source="Example", url=url)


def test_enrich_parses_bounded_article_and_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_ARTICLE_CACHE_PATH", str(tmp_path / "articles.json"))
    monkeypatch.setattr(ae, "allowed_url", lambda url: True)
    html = b"""
    <html><head><meta name='description' content='A supply disruption is reported.'></head>
    <body><nav>Ignore this</nav><h1>Supply update</h1>
    <p>The port closure reduces exports and may raise prices.</p><script>ignore()</script></body></html>
    """
    calls = []

    def fetch(url, timeout, max_bytes):
        calls.append((url, timeout, max_bytes))
        return html

    rows = ae.enrich([_headline()], now=NOW, fetch=fetch, excerpt_chars=200)
    row = next(iter(rows.values()))
    assert row["status"] == "OK"
    assert "port closure" in row["excerpt"]
    assert "Ignore this" not in row["excerpt"]
    assert calls and calls[0][1] == 5.0

    cached = ae.enrich([_headline()], now=NOW, fetch=lambda *_: (_ for _ in ()).throw(AssertionError()))
    assert next(iter(cached.values()))["status"] == "CACHED"
    assert ae.coverage([_headline()])["coverage_pct"] == 100.0


def test_enrich_skips_missing_and_private_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_ARTICLE_CACHE_PATH", str(tmp_path / "articles.json"))
    monkeypatch.setattr(ae, "allowed_url", lambda url: False)
    rows = ae.enrich([_headline("http://127.0.0.1/private"), _headline(None)], now=NOW,
                     fetch=lambda *_: b"never")
    row = next(iter(rows.values()))
    assert row["status"] == "SKIPPED_URL"
    assert ae.coverage([_headline(None)])["status"] == "EMPTY"
