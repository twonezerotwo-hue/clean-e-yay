"""Bounded, cached article evidence for the news shadow pipeline.

RSS titles remain the primary feed contract.  This module only adds a small,
read-only evidence layer for a bounded number of links during the discovery
refresh; publisher blocks fall back to the feed's bounded RSS summary. It
never raises into the ingestion or decision path and it never turns article
prose into an order by itself.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from packages.ops.store import write_text_atomic

_DEFAULT_PATH = "data/runtime/news_article_cache.json"
_USER_AGENT = "clean-e-yay/2.0 (paper-safe article evidence)"
_MAX_CACHE_ROWS = 600
_DEFAULT_TIMEOUT = 5.0
_DEFAULT_MAX_BYTES = 500_000
_DEFAULT_EXCERPT_CHARS = 1_200
_DEFAULT_TTL_HOURS = 6.0

FetchFn = Callable[[str, float, int], bytes]


def _path() -> Path:
    return Path(os.environ.get("NEWS_ARTICLE_CACHE_PATH", _DEFAULT_PATH))


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def cache_key(url: Any) -> str:
    return hashlib.sha256(str(url or "").strip().encode("utf-8")).hexdigest()[:24]


def _load() -> dict[str, Any]:
    try:
        payload = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "items": {}}


def _save(state: Mapping[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(state, ensure_ascii=False, default=str))


def _host_is_public(host: str) -> bool:
    host = host.strip("[]").casefold()
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        # A DNS failure is a fetch error, not an SSRF permission.  Returning
        # false avoids spending the request timeout on an invalid host.
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def allowed_url(url: Any) -> bool:
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and _host_is_public(parsed.hostname)


class _VisibleText(HTMLParser):
    _SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._title: list[str] = []
        self._description = ""
        self._parts: list[str] = []

    @property
    def title(self) -> str:
        return " ".join(self._title).strip()

    @property
    def description(self) -> str:
        return self._description.strip()

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self._SKIP:
            self._skip += 1
            return
        if tag == "meta":
            values = {str(k).casefold(): str(v or "").strip() for k, v in attrs}
            name = values.get("name", "").casefold()
            prop = values.get("property", "").casefold()
            if name in {"description", "og:description"} or prop == "og:description":
                self._description = values.get("content", "")[:2_000]

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip or not data.strip():
            return
        clean = html.unescape(data).strip()
        if not clean:
            return
        # Keep a title separately but also include paragraphs/headings in the
        # evidence excerpt.  The parser is intentionally not a boilerplate ML
        # remover; bounded text and the source URL are the audit boundary.
        self._parts.append(clean)
        if len(self._title) < 2 and len(clean) < 300:
            self._title.append(clean)


def _default_fetch(url: str, timeout: float, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(max_bytes + 1)


def _parse_article(raw: bytes, excerpt_chars: int, max_bytes: int) -> dict[str, Any] | None:
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    try:
        parser = _VisibleText()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = parser.text
    except Exception:
        return None
    if len(text) < 40:
        return None
    description = parser.description
    excerpt = (description + " " + text if description else text).strip()
    return {
        "title": parser.title[:240],
        "description": description[:500],
        "excerpt": excerpt[:excerpt_chars],
        "word_count": len(text.split()),
    }


def enrich(
    headlines: Iterable[Any],
    *,
    max_articles: int = 8,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    excerpt_chars: int = _DEFAULT_EXCERPT_CHARS,
    cache_ttl_hours: float = _DEFAULT_TTL_HOURS,
    now: datetime | None = None,
    fetch: FetchFn | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch a bounded set of public article pages and return evidence rows.

    Cached rows are reused first.  Missing/invalid URLs are represented with a
    status rather than raising; this makes the caller's refresh deterministic
    even when a publisher blocks automated readers.
    """
    now = now or datetime.now(UTC)
    state = _load()
    rows = dict(state.get("items") or {})
    out: dict[str, dict[str, Any]] = {}
    candidates = []
    for headline in headlines:
        url = str(getattr(headline, "url", None) or "").strip()
        if url:
            candidates.append((headline, url))
    candidates = candidates[: max(0, int(max_articles))]
    fetcher = fetch or _default_fetch
    to_fetch: list[tuple[str, Any, str, dict[str, Any], str | None]] = []
    for headline, url in candidates:
        key = cache_key(url)
        old = rows.get(key) if isinstance(rows.get(key), dict) else None
        fetched_at = _parse((old or {}).get("fetched_at"))
        if old and fetched_at and now - fetched_at <= timedelta(hours=float(cache_ttl_hours)):
            row = {**old, "status": "CACHED"}
            out[key] = row
            continue
        base = {
            "key": key,
            "url": url,
            "source": str(getattr(headline, "source", "") or ""),
            "headline_id": str(getattr(headline, "id", "") or ""),
            "fetched_at": _iso(now),
        }
        summary = str(getattr(headline, "article_summary", "") or "").strip()
        if not allowed_url(url):
            row = ({**base, "status": "RSS_SUMMARY", "excerpt": summary[:excerpt_chars],
                    "description": summary[:500], "word_count": len(summary.split())}
                   if len(summary) >= 80 else {**base, "status": "SKIPPED_URL"})
            rows[key] = row
            out[key] = row
        else:
            to_fetch.append((key, headline, url, base, summary if len(summary) >= 80 else None))

    def _fetch_one(item: tuple[str, Any, str, dict[str, Any], str | None]) -> tuple[str, dict[str, Any]]:
        key, _headline, url, base, summary = item
        try:
            raw = fetcher(url, float(timeout_seconds), int(max_bytes))
            parsed = _parse_article(raw, int(excerpt_chars), int(max_bytes))
            if parsed:
                row = {**base, **parsed, "status": "OK"}
            elif summary:
                row = {**base, "status": "RSS_SUMMARY", "excerpt": summary[:excerpt_chars],
                       "description": summary[:500], "word_count": len(summary.split())}
            else:
                row = {**base, "status": "PARSE_ERROR"}
        except Exception as exc:
            if summary:
                row = {**base, "status": "RSS_SUMMARY", "excerpt": summary[:excerpt_chars],
                       "description": summary[:500], "word_count": len(summary.split()),
                       "fetch_error": type(exc).__name__}
            else:
                row = {**base, "status": "FETCH_ERROR", "error": type(exc).__name__}
        return key, row

    # Article retrieval is off the decision path. A small pool prevents a
    # blocked publisher from serially adding max_articles × timeout to the
    # learning cycle while keeping the network fan-out bounded.
    if to_fetch:
        with ThreadPoolExecutor(max_workers=min(4, len(to_fetch))) as pool:
            futures = [pool.submit(_fetch_one, item) for item in to_fetch]
            for future in as_completed(futures):
                key, row = future.result()
                rows[key] = row
                out[key] = row
    if len(rows) > _MAX_CACHE_ROWS:
        rows = dict(sorted(rows.items(), key=lambda item: str((item[1] or {}).get("fetched_at", "")), reverse=True)[:_MAX_CACHE_ROWS])
    state = {"schema_version": 1, "items": rows}
    _save(state)
    return out


def coverage(headlines: Iterable[Any]) -> dict[str, Any]:
    """Read-only cache coverage for the currently visible RSS headlines."""
    rows = _load().get("items") or {}
    urls = [str(getattr(h, "url", None) or "").strip() for h in headlines]
    urls = [u for u in urls if u]
    cached = [rows.get(cache_key(url)) for url in urls if isinstance(rows.get(cache_key(url)), dict)]
    ok = [row for row in cached if row.get("status") in {"OK", "CACHED", "RSS_SUMMARY"} and row.get("excerpt")]
    return {
        "headline_urls": len(urls),
        "cached_articles": len(ok),
        "coverage_pct": round(len(ok) / len(urls) * 100, 1) if urls else 0.0,
        "last_fetched_at": max((str(row.get("fetched_at")) for row in ok), default=None),
        "status": "PARTIAL" if ok and len(ok) < len(urls) else "READY" if ok else "EMPTY",
    }


def cached(urls: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Return cached evidence without performing network I/O."""
    rows = _load().get("items") or {}
    out: dict[str, dict[str, Any]] = {}
    for url in urls:
        value = str(url or "").strip()
        row = rows.get(cache_key(value)) if value else None
        if isinstance(row, dict) and row.get("excerpt"):
            out[value] = row
    return out


def context_for(headline: Any, *, article_rows: Mapping[str, Mapping[str, Any]] | None = None) -> tuple[str, dict[str, Any] | None]:
    """Return the bounded text available for deterministic article analysis.

    RSS title remains the primary identity.  A cached article excerpt is an
    additive evidence source only; this helper never performs network I/O and
    therefore cannot stall or bypass the existing decision path.
    """
    title = str(getattr(headline, "title", "") or "").strip()
    title_tr = str(getattr(headline, "title_tr", "") or "").strip()
    url = str(getattr(headline, "url", "") or "").strip()
    rows = article_rows if article_rows is not None else cached([url])
    row = rows.get(url) if url else None
    excerpt = str((row or {}).get("excerpt", "") or "").strip()
    if not excerpt:
        summary = str(getattr(headline, "article_summary", "") or "").strip()
        if len(summary) >= 80:
            excerpt = summary[:_DEFAULT_EXCERPT_CHARS]
            row = {
                "status": "RSS_SUMMARY",
                "url": url or None,
                "excerpt": excerpt,
                "word_count": len(summary.split()),
            }
    parts = [part for part in (title, title_tr, excerpt) if part]
    return " ".join(parts), dict(row) if isinstance(row, Mapping) else None


__all__ = ["allowed_url", "cache_key", "cached", "context_for", "coverage", "enrich"]
