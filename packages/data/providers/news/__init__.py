"""Haber orchestrator — gerçek RSS + geo-news (P0 legacy parity).

Politika ([docs/DATA_POLICY.md]):
- Runtime'da **mock headline yasaktır**. Feed'ler başarısız olursa boş
  liste döner; pipeline `news_unavailable` warning ekler, consensus news
  skoru nötr 50 kalır, provider status DEGRADED görünür.
- Fixture başlıklar yalnızca test/dev path (`TEST_USE_MOCK=true` veya
  `NEWS_USE_FIXTURE=true`) ve `verified=False` damgalı — karar zincirine
  girmezler.

İki feed grubu vardır: market (finansal) + geo (jeopolitik bağlam).
Geo-news karar verici değildir; bölge/CAUTION bağlamı sağlar.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime

from packages.data.providers.news import fixtures, rss
from packages.data.types import NewsHeadline

_PROVIDER_NAMES = ("news", "geo_news")

_LOCK = threading.Lock()
_STATUS: dict[str, dict] = {
    name: {
        "status": "unknown",
        "last_success_at": None,
        "last_error": None,
        "calls": 0,
        "fallbacks": 0,
    }
    for name in _PROVIDER_NAMES
}

# Mini cache — sayfa yenilemelerinde feed'leri tekrar tekrar çekmemek için.
_CACHE: tuple[float, list[NewsHeadline]] | None = None
_CACHE_TTL_SEC = 120.0


def _truthy(v: str | None) -> bool:
    return (v or "").lower() == "true"


def is_fixture_mode() -> bool:
    """Test/dev fixture path açık mı? Runtime'da false kalmalıdır."""
    return _truthy(os.environ.get("TEST_USE_MOCK")) or _truthy(
        os.environ.get("NEWS_USE_FIXTURE")
    )


def _mark(name: str, *, ok: bool, error: str | None = None) -> None:
    with _LOCK:
        st = _STATUS[name]
        st["calls"] += 1
        if ok:
            st["status"] = "ok"
            st["last_success_at"] = datetime.now(UTC).isoformat()
            st["last_error"] = None
        else:
            st["status"] = "degraded"
            if error:
                st["last_error"] = error


def get_provider_status() -> dict[str, dict]:
    with _LOCK:
        return {k: dict(v) for k, v in _STATUS.items()}


def reset_provider_status() -> None:
    global _CACHE
    with _LOCK:
        for v in _STATUS.values():
            v.update(
                status="unknown",
                last_success_at=None,
                last_error=None,
                calls=0,
                fallbacks=0,
            )
    _CACHE = None


def _dedup(headlines: list[NewsHeadline]) -> list[NewsHeadline]:
    seen: set[str] = set()
    out: list[NewsHeadline] = []
    for h in headlines:
        key = h.title.lower().strip()[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


_RELEVANCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _sort_key(h: NewsHeadline) -> tuple[int, float]:
    from packages.data.providers.news import classify

    rel = classify.classify_relevance(classify.classify_tags(h.title))
    return (_RELEVANCE_ORDER.get(rel, 3), -h.ts.timestamp())


def list_headlines(limit: int = 14, fetch_fn: rss.FetchFn | None = None) -> list[NewsHeadline]:
    """Doğrulanmış (verified=True) gerçek başlıklar. Veri yoksa boş liste —
    asla mock, asla crash."""
    global _CACHE
    if is_fixture_mode():
        return fixtures.list_headlines(limit)

    now_m = time.monotonic()
    if fetch_fn is None and _CACHE is not None and (now_m - _CACHE[0]) < _CACHE_TTL_SEC:
        return _CACHE[1][:limit]

    market, market_ok, market_err = rss.fetch_feed_group(rss.MARKET_FEEDS, fetch_fn=fetch_fn)
    geo, geo_ok, geo_err = rss.fetch_feed_group(rss.GEO_FEEDS, geo=True, fetch_fn=fetch_fn)
    _mark(
        "news",
        ok=market_ok > 0,
        error=market_err or ("no fresh headlines" if not market else None),
    )
    _mark(
        "geo_news",
        ok=geo_ok > 0,
        error=geo_err or ("no fresh geo headlines" if not geo else None),
    )

    merged = _dedup(market + geo)
    merged.sort(key=_sort_key)

    if fetch_fn is None:
        _CACHE = (now_m, merged)
    return merged[:limit]
