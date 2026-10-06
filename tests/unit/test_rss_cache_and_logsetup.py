"""B4 (paylaşılan RSS önbelleği) + UTF-8 log kurulumu — regresyon testleri."""
from __future__ import annotations

import io

from packages.data.providers.news import rss
from packages.ops import logsetup

# ── (1) RSS: aynı URL iki çağrıda BİR kez indirilir ──────────────────────────

def test_rss_feed_cache_shares_downloads_across_callers(monkeypatch):
    rss.reset_cache()
    calls: list[str] = []

    def _fake(url: str) -> str:
        calls.append(url)
        return "<rss><channel></channel></rss>"

    monkeypatch.setattr(rss, "default_fetch", _fake)
    feeds = ({"url": "https://example.com/a.xml", "source": "X"},)
    # Tick + haber keşfi aynı kaynağı çeker → ilk seferde indir, sonra önbellekten.
    rss.fetch_feed_group(feeds, geo=False)
    rss.fetch_feed_group(feeds, geo=False)
    rss.fetch_feed_group(feeds, geo=False)
    assert calls == ["https://example.com/a.xml"]  # 3 çağrı, 1 indirme
    rss.reset_cache()
    rss.fetch_feed_group(feeds, geo=False)
    assert len(calls) == 2  # reset sonrası yeniden indirir
    rss.reset_cache()


def test_rss_injected_fetch_fn_bypasses_cache(monkeypatch):
    rss.reset_cache()
    calls: list[str] = []

    def _injected(url: str) -> str:
        calls.append(url)
        return "<rss><channel></channel></rss>"

    feeds = ({"url": "https://example.com/b.xml", "source": "Y"},)
    rss.fetch_feed_group(feeds, fetch_fn=_injected)
    rss.fetch_feed_group(feeds, fetch_fn=_injected)
    assert len(calls) == 2  # enjekte edilen fetch_fn önbelleğe girmez (testler)
    rss.reset_cache()


def test_news_reset_provider_status_clears_feed_cache(monkeypatch):
    from packages.data.providers import news

    rss.reset_cache()
    calls: list[str] = []

    def _fake(url: str) -> str:
        calls.append(url)
        return "<rss><channel></channel></rss>"

    monkeypatch.setattr(rss, "default_fetch", _fake)
    feeds = ({"url": "https://example.com/c.xml", "source": "Z"},)
    rss.fetch_feed_group(feeds, geo=False)
    news.reset_provider_status()
    rss.fetch_feed_group(feeds, geo=False)
    assert len(calls) == 2  # reset sonrası önbellek boş → yeniden indirir
    rss.reset_cache()


# ── (2) UTF-8 log kurulumu ───────────────────────────────────────────────────

def test_enable_utf8_output_reconfigures_streams(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1254")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp1254")
    monkeypatch.setattr(logsetup.sys, "stdout", out)
    monkeypatch.setattr(logsetup.sys, "stderr", err)
    logsetup.enable_utf8_output()
    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"


def test_configure_logging_is_callable_and_idempotent():
    logsetup.configure_logging()
    logsetup.configure_logging()  # ikinci çağrı patlamamalı (basicConfig no-op)
