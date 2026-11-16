"""Benzinga haber sağlayıcısı: ayrıştırma, sembol etiketi kuralı, anahtarsız/hatalı durum, akışa bağlanma."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.data.providers import news
from packages.data.providers.news import benzinga, first_seen
from packages.data.providers.news.provenance import source_family

NOW = datetime(2026, 11, 13, 17, 30, tzinfo=UTC)
KNOWN = {"NVDA", "BTCUSD", "ETHUSD", "XLK"}


def _item(title: str, minutes_ago: float, stocks=(), url="https://www.benzinga.com/news/x") -> dict:
    created = (NOW - timedelta(minutes=minutes_ago)).astimezone(UTC)
    # Benzinga zaman biçimi: RFC 2822, -0400
    local = created - timedelta(hours=4)
    return {"id": 1, "title": title, "created": local.strftime("%a, %d %b %Y %H:%M:%S -0400"),
            "url": url, "stocks": [{"name": s} for s in stocks], "channels": [{"name": "News"}]}


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWS_FIRST_SEEN_PATH", str(tmp_path / "fs.jsonl"))
    first_seen.reset()
    benzinga.reset_cache()
    yield
    benzinga.reset_cache()
    first_seen.reset()


def test_parse_keeps_fresh_items_and_reads_rfc2822_timestamps() -> None:
    heads = benzinga.parse([_item("Nvidia shares slide after CEO exit", 6.5, ["NVDA"]),
                            _item("Old story", 60 * 30), {"title": "No date"}], now=NOW, symbols=KNOWN)
    assert [h.title for h in heads] == ["Nvidia shares slide after CEO exit"]
    h = heads[0]
    assert h.source == "Benzinga" and h.verified
    assert (NOW - h.ts) == timedelta(minutes=6.5)
    assert h.asset_impact.get("NVDA") == -1.0


def test_ticker_tags_only_for_company_specific_stories() -> None:
    single = benzinga.parse([_item("Company X beats estimates, raises outlook", 3, ["XLK"])], now=NOW, symbols=KNOWN)[0]
    assert single.asset_impact.get("XLK") == 1.0
    wrap = benzinga.parse([_item("Futures edge higher ahead of retail sales data", 3, ["XLK", "NVDA", "SPY", "QQQ"])],
                          now=NOW, symbols=KNOWN)[0]
    assert "XLK" not in wrap.asset_impact and "NVDA" not in wrap.asset_impact  # piyasa özeti: yön taşınmaz
    # Genel sınıf kelimesi ("shares") hisse ETF'lerini etiketlese de açık sembol 4-etki sınırında kalır
    named = benzinga.parse([_item("Nvidia shares slide after CEO exit", 3, ["NVDA"])], now=NOW, symbols=KNOWN)[0]
    assert next(iter(named.asset_impact)) == "NVDA" and len(named.asset_impact) <= 4
    crypto = benzinga.parse([_item("Bitcoin rallies past resistance", 3, ["BTC/USD"])], now=NOW, symbols=KNOWN)[0]
    assert crypto.asset_impact.get("BTCUSD") == 1.0
    # Başlıkta ad geçmese de Benzinga'nın sembol listesi BTC/USD → BTCUSD olarak bağlanır
    etf = benzinga.parse([_item("Spot ETF inflows set a record as institutions add exposure", 3, ["BTC/USD"])],
                         now=NOW, symbols=KNOWN)[0]
    assert "BTCUSD" in etf.asset_impact
    unknown = benzinga.parse([_item("Acme surges on deal", 3, ["ACME"])], now=NOW, symbols=KNOWN)[0]
    assert "ACME" not in unknown.asset_impact  # kayıtta olmayan sembol uydurulmaz


def test_no_key_means_no_call(monkeypatch) -> None:
    monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
    called = []
    assert benzinga.fetch_headlines(fetch=lambda k: called.append(k) or []) == []
    assert called == []


def test_errors_never_break_the_feed(monkeypatch) -> None:
    monkeypatch.setenv("BENZINGA_API_KEY", "test-key")

    def boom(key):
        raise TimeoutError("slow")

    assert benzinga.fetch_headlines(fetch=boom, now=NOW) == []
    assert benzinga.last_error() == "TimeoutError"


def test_injected_fetch_neither_records_nor_caches(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BENZINGA_API_KEY", "test-key")
    fresh = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    heads = benzinga.fetch_headlines(fetch=lambda k: [{"title": "Gold edges higher", "created": fresh}])
    assert [h.title for h in heads] == ["Gold edges higher"]
    assert not (tmp_path / "fs.jsonl").exists()
    calls = []
    monkeypatch.setattr(benzinga, "_default_fetch", lambda k: calls.append(k) or [])
    benzinga.fetch_headlines()
    assert calls == ["test-key"]  # enjekte çağrı önbelleğe yazmamıştı


def test_default_path_records_first_seen_and_caches(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BENZINGA_API_KEY", "test-key")
    calls = []
    fresh = datetime.now(UTC)

    def fake(key):
        calls.append(key)
        return [{"title": "Nvidia board weighs CEO succession", "created": fresh.strftime("%a, %d %b %Y %H:%M:%S +0000"),
                 "stocks": [{"name": "NVDA"}]}]

    monkeypatch.setattr(benzinga, "_default_fetch", fake)
    first = benzinga.fetch_headlines()
    second = benzinga.fetch_headlines()
    assert len(first) == 1 and [h.title for h in second] == [h.title for h in first]
    assert calls == ["test-key"]  # 60 sn önbellek
    rows = [json.loads(x) for x in (tmp_path / "fs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["source"] == "Benzinga" and rows[0]["group"] == "market" and rows[0]["family"] == "direct:benzinga.com"


def test_list_headlines_merges_benzinga_but_never_in_injected_test_fetch(monkeypatch) -> None:
    pub = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = f"<rss><channel><item><title>Gold edges higher</title><pubDate>{pub}</pubDate></item></channel></rss>"

    monkeypatch.setenv("TEST_USE_MOCK", "false")  # test takımı haberi sahte veri modunda tutar; gerçek yol sınansın
    monkeypatch.setenv("NEWS_USE_FIXTURE", "false")

    def must_not_call(**_):
        raise AssertionError("enjekte edilen getirmede Benzinga çağrılmamalı")

    monkeypatch.setattr(benzinga, "fetch_headlines", must_not_call)
    news.reset_provider_status()
    assert news.list_headlines(limit=50, fetch_fn=lambda url: xml)

    bz_head = benzinga.parse([{"title": "Nvidia shares slide after CEO exit", "created": pub, "stocks": [{"name": "NVDA"}]}],
                             symbols={"NVDA"})
    monkeypatch.setattr(benzinga, "fetch_headlines", lambda **_: bz_head)
    monkeypatch.setattr("packages.data.providers.news.rss.fetch_feed_group", lambda feeds, **kw: ([], 0, "down"))
    news.reset_provider_status()
    merged = news.list_headlines(limit=50)
    assert [h.source for h in merged] == ["Benzinga"]
    assert news.get_provider_status()["news"]["status"] == "ok"  # RSS düşük olsa da Benzinga başlık verdi
    news.reset_provider_status()


def test_benzinga_is_its_own_publisher_family() -> None:
    assert source_family("Benzinga") == "direct:benzinga.com"
    assert source_family("Benzinga", url="https://www.benzinga.com/news/25/11/x") == "direct:benzinga.com"
