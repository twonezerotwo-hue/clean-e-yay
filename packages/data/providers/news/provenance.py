"""News provenance and cross-source consensus helpers.

RSS feeds in this project contain both direct publisher feeds and Google News
query feeds.  A query feed is a transport bucket, not an independent
newsroom.  This module gives every consumer the same conservative vocabulary
for publisher families and story clusters without changing the trading
decision path.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

# These labels are query/proxy buckets in rss.py, not direct publisher feeds.
_PROXY_BUCKETS = {
    "google news": "google_news:redirect",
    "reuters": "google_news:reuters_query",
    "bloomberg/ft": "google_news:bloomberg_ft_query",
    "gold wire": "google_news:metals_query",
    "world wire": "google_news:world_query",
    # These are five query views over the same Google News transport.  Keep
    # their UI labels distinct but count them as one provenance family so a
    # story repeated across focus queries cannot fake independent confirmation.
    "us foreign affairs": "google_news:foreign_affairs_query",
    "iran foreign affairs": "google_news:foreign_affairs_query",
    "china foreign affairs": "google_news:foreign_affairs_query",
    "russia foreign affairs": "google_news:foreign_affairs_query",
    "israel foreign affairs": "google_news:foreign_affairs_query",
}

# A feed label is presentation data, not a publisher identity.  The same
# newsroom currently arrives from RSS, Google News and topic-specific feeds
# under several labels (for example ``Seeking Alpha`` and
# ``seekingalpha.com``).  Keep one canonical family so a story is not counted
# as several independent confirmations.
_PUBLISHER_ALIASES = {
    "seeking alpha": "direct:seekingalpha.com",
    "seekingalpha": "direct:seekingalpha.com",
    "seekingalpha.com": "direct:seekingalpha.com",
    "investing": "direct:investing.com",
    "investing.com": "direct:investing.com",
    "investing emtia": "direct:investing.com",
    "investing fx": "direct:investing.com",
    "investing markets": "direct:investing.com",
    "cnbc": "direct:cnbc.com",
    "cnbc.com": "direct:cnbc.com",
    "cnbc economy": "direct:cnbc.com",
    "cointelegraph": "direct:cointelegraph.com",
    "cointelegraph.com": "direct:cointelegraph.com",
    "coindesk": "direct:coindesk.com",
    "coindesk.com": "direct:coindesk.com",
    "the block": "direct:theblock.co",
    "theblock.co": "direct:theblock.co",
    "cryptoslate": "direct:cryptoslate.com",
    "cryptoslate.com": "direct:cryptoslate.com",
    "bitcoin.com": "direct:news.bitcoin.com",
    "news.bitcoin.com": "direct:news.bitcoin.com",
    "crypto potato": "direct:cryptopotato.com",
    "cryptopotato.com": "direct:cryptopotato.com",
    "the defiant": "direct:thedefiant.io",
    "thedefiant.io": "direct:thedefiant.io",
    "u.today": "direct:u.today",
    "u today": "direct:u.today",
    "yahoo finance": "direct:finance.yahoo.com",
    "finance.yahoo.com": "direct:finance.yahoo.com",
    "al jazeera": "direct:aljazeera.com",
    "aljazeera.com": "direct:aljazeera.com",
}

_HOST_ALIASES = {
    "seekingalpha.com": "direct:seekingalpha.com",
    "www.seekingalpha.com": "direct:seekingalpha.com",
    "investing.com": "direct:investing.com",
    "www.investing.com": "direct:investing.com",
    "cnbc.com": "direct:cnbc.com",
    "www.cnbc.com": "direct:cnbc.com",
    "cointelegraph.com": "direct:cointelegraph.com",
    "www.cointelegraph.com": "direct:cointelegraph.com",
    "coindesk.com": "direct:coindesk.com",
    "www.coindesk.com": "direct:coindesk.com",
    "theblock.co": "direct:theblock.co",
    "www.theblock.co": "direct:theblock.co",
    "cryptoslate.com": "direct:cryptoslate.com",
    "www.cryptoslate.com": "direct:cryptoslate.com",
    "news.bitcoin.com": "direct:news.bitcoin.com",
    "bitcoin.com": "direct:news.bitcoin.com",
    "cryptopotato.com": "direct:cryptopotato.com",
    "www.cryptopotato.com": "direct:cryptopotato.com",
    "thedefiant.io": "direct:thedefiant.io",
    "www.thedefiant.io": "direct:thedefiant.io",
    "u.today": "direct:u.today",
    "www.u.today": "direct:u.today",
    "finance.yahoo.com": "direct:finance.yahoo.com",
    "feeds.finance.yahoo.com": "direct:finance.yahoo.com",
    "aljazeera.com": "direct:aljazeera.com",
    "www.aljazeera.com": "direct:aljazeera.com",
}

_STOPWORDS = {
    "the", "and", "for", "from", "says", "said", "with", "could", "may",
    "might", "this", "that", "over", "after", "amid", "into", "bir", "ile",
    "için", "ve", "olan", "olanı", "news", "report", "reports",
}
_SYNONYMS = {
    "tehran": "iran", "warns": "threat", "warned": "threat",
    "threatens": "threat", "threatening": "threat", "shut": "close",
    "closed": "close", "halted": "halt",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def story_key(text: Any) -> str:
    """Stable, conservative key for light syndication rewrites.

    It intentionally remains a token key rather than a semantic LLM merge:
    unrelated stories with only a common asset must not be collapsed.
    """
    tokens = [
        _SYNONYMS.get(token, token)
        for token in re.findall(r"[\w']+", _clean(text).casefold())
        if len(token) > 2 and token not in _STOPWORDS
    ]
    return " ".join(sorted(set(tokens)))


def source_family(source: Any, *, title: Any = None, url: Any = None) -> str:
    """Return an independence family, not merely the UI feed label."""
    label = _clean(source)
    low = label.casefold()
    if low in _PROXY_BUCKETS:
        # The query bucket is the independence family.  A publisher suffix is
        # useful for display, but must not turn one Google News query into
        # several independent confirmations.
        return _PROXY_BUCKETS[low]
    if low.startswith("http"):
        host = urlparse(low).netloc.casefold() or low
        if host == "news.google.com":
            return "google_news:redirect"
        return _HOST_ALIASES.get(host, f"direct:{host.removeprefix('www.')}")
    host = urlparse(_clean(url)).netloc if _clean(url).startswith("http") else ""
    if host:
        host = host.casefold()
        if host == "news.google.com":
            return "google_news:redirect"
        return _HOST_ALIASES.get(host, f"direct:{host.removeprefix('www.')}")
    if low in _PUBLISHER_ALIASES:
        return _PUBLISHER_ALIASES[low]
    # Legacy event-study rows persisted values such as
    # ``direct:seeking_alpha``.  Read them through the same canonical map so
    # historical evidence joins the new buckets instead of silently starting
    # a second publisher family.
    legacy_label = low.removeprefix("direct:")
    legacy_alias = _PUBLISHER_ALIASES.get(legacy_label) or _PUBLISHER_ALIASES.get(
        legacy_label.replace("_", " ")
    )
    if legacy_alias:
        return legacy_alias
    if "official" in low:
        return "direct:official"
    if "ministry" in low:
        return "direct:ministry"
    if "government" in low:
        return "direct:government"
    normalized = re.sub(r"[^a-z0-9]+", "_", low).strip("_") or "unknown"
    return f"direct:{normalized}"


def is_proxy_source(source: Any) -> bool:
    low = _clean(source).casefold()
    if low in _PROXY_BUCKETS:
        return True
    if low.startswith("http"):
        return (urlparse(low).netloc or "").casefold() == "news.google.com"
    return False


def _direction(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if number > 0:
        return "bullish"
    if number < 0:
        return "bearish"
    return "neutral"


def build_consensus(headlines: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Create an evidence-calibrated, read-only news consensus report.

    Counts are story/family aware: repeated titles from one proxy bucket do
    not masquerade as independent confirmation.  Conflicting stories are
    explicitly retained and marked ``MIXED``; no direction is silently chosen.
    """
    now = now or datetime.now(UTC)
    rows = [h for h in headlines if getattr(h, "verified", False)]
    stories: dict[str, dict[str, Any]] = {}
    assets: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "bullish_stories": set(), "bearish_stories": set(), "neutral_stories": set(),
        "bullish_families": set(), "bearish_families": set(), "all_families": set(),
    })
    for h in rows:
        title = _clean(getattr(h, "title", ""))
        key = story_key(title) or f"headline:{getattr(h, 'id', '')}"
        family = source_family(getattr(h, "source", None), title=title, url=getattr(h, "url", None))
        bucket = stories.setdefault(key, {"story_key": key, "titles": set(), "sources": set(),
                                           "families": set(), "proxy": False, "directions": defaultdict(set),
                                           "headlines": 0})
        bucket["titles"].add(title)
        bucket["sources"].add(_clean(getattr(h, "source", "unknown")))
        bucket["families"].add(family)
        bucket["proxy"] = bucket["proxy"] or is_proxy_source(getattr(h, "source", None))
        bucket["headlines"] += 1
        for symbol, impact in (getattr(h, "asset_impact", None) or {}).items():
            direction = _direction(impact)
            bucket["directions"][symbol].add(direction)
            a = assets[str(symbol)]
            a["all_families"].add(family)
            if direction == "bullish":
                a["bullish_stories"].add(key)
                a["bullish_families"].add(family)
            elif direction == "bearish":
                a["bearish_stories"].add(key)
                a["bearish_families"].add(family)
            else:
                a["neutral_stories"].add(key)

    story_rows = []
    for item in stories.values():
        directions = {symbol: sorted(values) for symbol, values in item["directions"].items()}
        story_rows.append({
            "story_key": item["story_key"],
            "title": sorted(item["titles"])[0] if item["titles"] else "",
            "source_labels": sorted(item["sources"]),
            "source_families": sorted(item["families"]),
            "proxy_bucket": item["proxy"],
            "headline_count": item["headlines"],
            "asset_directions": directions,
            "same_story_conflict": any(len(values) > 1 for values in directions.values()),
        })
    asset_rows = []
    for symbol, item in sorted(assets.items()):
        bull = len(item["bullish_stories"])
        bear = len(item["bearish_stories"])
        if bull and bear:
            consensus = "MIXED"
        elif bull:
            consensus = "BULLISH"
        elif bear:
            consensus = "BEARISH"
        else:
            consensus = "NEUTRAL"
        total_directional = bull + bear
        asset_rows.append({
            "symbol": symbol,
            "consensus": consensus,
            "bullish_stories": bull,
            "bearish_stories": bear,
            "neutral_stories": len(item["neutral_stories"]),
            "bullish_independent_families": len(item["bullish_families"]),
            "bearish_independent_families": len(item["bearish_families"]),
            "independent_source_families": len(item["all_families"]),
            "conflict": bool(bull and bear),
            "evidence_status": "CONFLICT" if bull and bear else "CONFIRMED" if total_directional and len(item["all_families"]) >= 2 else "SINGLE_SOURCE",
        })
    timestamps = [getattr(h, "ts", None) for h in rows if getattr(h, "ts", None)]
    newest = max(timestamps).isoformat() if timestamps else None
    source_labels = {_clean(getattr(h, "source", "unknown")) for h in rows}
    families = {source_family(getattr(h, "source", None), title=getattr(h, "title", None), url=getattr(h, "url", None)) for h in rows}
    proxy_count = sum(1 for h in rows if is_proxy_source(getattr(h, "source", None)))
    return {
        "generated_at": now.isoformat(),
        "headline_count": len(rows),
        "unique_source_labels": len(source_labels),
        "independent_source_families": len(families),
        "proxy_headline_count": proxy_count,
        "proxy_share": round(proxy_count / len(rows), 3) if rows else 0.0,
        "story_count": len(stories),
        "newest_headline_at": newest,
        "stories": sorted(story_rows, key=lambda row: row["title"]),
        "assets": asset_rows,
        "policy": {
            "conflict_handling": "MIXED → no direction is selected; evidence remains visible",
            "independence_rule": "same publisher/proxy family counts once",
            "decision_effect": "observe_only",
        },
    }


__all__ = ["build_consensus", "is_proxy_source", "source_family", "story_key"]
