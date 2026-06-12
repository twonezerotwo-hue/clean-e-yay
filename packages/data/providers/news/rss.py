"""RSS/Atom çekme ve ayrıştırma — eski Codex news/geo provider portu.

Stdlib-only (urllib + ElementTree). Her hata yutulur ve boş liste döner:
network fail asla crash etmez, mock'a asla düşülmez (DATA_POLICY).
"""
from __future__ import annotations

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from packages.data.providers.news import classify
from packages.data.types import NewsHeadline

TIMEOUT_SEC = 8.0
MAX_AGE_HOURS: Final[int] = 24      # taze haber kuralı (legacy parity)
MAX_PER_FEED: Final[int] = 6

FetchFn = Callable[[str], str]

# ---------------------------------------------------------------------------
# Feed tanımları — anahtar gerektirmeyen, herkese açık RSS'ler
# ---------------------------------------------------------------------------

MARKET_FEEDS: Final[tuple[dict[str, str], ...]] = (
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "source": "CNBC"},
    {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "source": "CNBC Economy"},
    {"url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "source": "MarketWatch"},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "CoinDesk"},
    {"url": "https://cointelegraph.com/rss", "source": "Cointelegraph"},
    {"url": "https://www.federalreserve.gov/feeds/press_all.xml", "source": "Fed Reserve"},
    {
        "url": (
            "https://news.google.com/rss/search?q=when:1d+site:reuters.com+"
            "(markets+OR+fed+OR+oil+OR+gold+OR+crypto)&hl=en-US&gl=US&ceid=US:en"
        ),
        "source": "Reuters",
    },
)

GEO_FEEDS: Final[tuple[dict[str, str], ...]] = (
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC World"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera"},
    {"url": "https://www.jpost.com/Rss/RssFeedsHeadlines.aspx", "source": "Jerusalem Post"},
    {
        "url": (
            "https://news.google.com/rss/search?q=when:1d+(geopolitics+OR+iran+OR+"
            "israel+OR+ukraine+OR+taiwan+OR+opec)&hl=en-US&gl=US&ceid=US:en"
        ),
        "source": "World Wire",
    },
)


def default_fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "clean-e-yay/2.0 (paper-safe news reader)"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Tarih ayrıştırma — RFC-2822 + ISO-8601 + yaygın varyantlar
# ---------------------------------------------------------------------------

def parse_pub_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()

    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
    except Exception:
        pass

    iso_try = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_try)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S %z",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Feed ayrıştırma
# ---------------------------------------------------------------------------

_NS = {"atom": "http://www.w3.org/2005/Atom"}
_DATE_TAGS = (
    "pubDate",
    "atom:published",
    "published",
    "{http://purl.org/dc/elements/1.1/}date",
    "updated",
)


def parse_feed(
    xml_text: str,
    source: str,
    *,
    geo: bool = False,
    now: datetime | None = None,
) -> list[NewsHeadline]:
    """Tek feed'in XML'ini NewsHeadline listesine çevirir.

    Tarihsiz veya 24 saatten eski item'lar atılır (legacy "şimdiki zaman
    yalanı" bug fix'i korunur). Geo feed'lerde bölge tespit edilemeyen
    item'lar elenir.
    """
    out: list[NewsHeadline] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out

    items = root.findall(".//item") or root.findall(".//atom:entry", _NS)
    now_utc = now or datetime.now(UTC)
    raw_items: list[tuple[datetime, NewsHeadline]] = []

    for item in items[:25]:
        title_el = item.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title or classify.is_irrelevant(title):
            continue

        link_el = item.find("link")
        url = ""
        if link_el is not None:
            url = (link_el.text or link_el.get("href", "") or "").strip()

        pub_el = None
        for tag in _DATE_TAGS:
            candidate = item.find(tag, _NS) if ":" in tag else item.find(tag)
            if candidate is not None:
                pub_el = candidate
                break
        raw_date = (pub_el.text or "").strip() if pub_el is not None else ""
        pub_dt = parse_pub_date(raw_date)
        if pub_dt is None:
            continue
        age_h = (now_utc - pub_dt).total_seconds() / 3600
        if age_h > MAX_AGE_HOURS or age_h < -1:
            continue

        region = classify.detect_region(title)
        if geo and region is None:
            continue
        sentiment = classify.classify_sentiment(title)
        hid = hashlib.sha1(f"{source}|{title}".encode()).hexdigest()[:12]
        raw_items.append(
            (
                pub_dt,
                NewsHeadline(
                    id=hid,
                    source=source,
                    region=region,
                    ts=pub_dt,
                    title=title,
                    sentiment=sentiment,
                    asset_impact=classify.classify_asset_impact(title, sentiment),
                    url=url or None,
                    verified=True,
                    freshness=classify.freshness_of(pub_dt, now_utc),
                ),
            )
        )

    raw_items.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in raw_items[:MAX_PER_FEED]]


def fetch_feed_group(
    feeds: tuple[dict[str, str], ...],
    *,
    geo: bool = False,
    fetch_fn: FetchFn | None = None,
) -> tuple[list[NewsHeadline], int, str | None]:
    """Feed grubunu paralel çeker. Döner: (headlines, ok_feed_count, last_error)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    fetch = fetch_fn or default_fetch
    headlines: list[NewsHeadline] = []
    ok = 0
    last_error: str | None = None

    def _one(feed: dict[str, str]) -> tuple[list[NewsHeadline], str | None]:
        try:
            xml_text = fetch(feed["url"])
            return parse_feed(xml_text, feed["source"], geo=geo), None
        except Exception as exc:
            return [], f"{feed['source']}: {str(exc)[:120]}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_one, f) for f in feeds]
        for fut in as_completed(futures):
            parsed, err = fut.result()
            if err is not None:
                last_error = err
            elif parsed:
                ok += 1
            headlines.extend(parsed)

    return headlines, ok, last_error
