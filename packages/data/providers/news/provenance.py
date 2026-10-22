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
    "reuters": "google_news:reuters_query",
    "bloomberg/ft": "google_news:bloomberg_ft_query",
    "gold wire": "google_news:metals_query",
    "world wire": "google_news:world_query",
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
        host = urlparse(low).netloc or low
        return f"direct:{host.removeprefix('www.')}"
    host = urlparse(_clean(url)).netloc if _clean(url).startswith("http") else ""
    if host:
        return f"direct:{host.removeprefix('www.')}"
    if "official" in low:
        return "direct:official"
    if "ministry" in low:
        return "direct:ministry"
    if "government" in low:
        return "direct:government"
    normalized = re.sub(r"[^a-z0-9]+", "_", low).strip("_") or "unknown"
    return f"direct:{normalized}"


def is_proxy_source(source: Any) -> bool:
    return _clean(source).casefold() in _PROXY_BUCKETS


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
