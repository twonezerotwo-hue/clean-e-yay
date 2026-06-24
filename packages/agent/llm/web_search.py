"""Read-only web search adapter for chat grounding.

The adapter is intentionally narrow: it only retrieves public search snippets and
never feeds trading decision logic. Missing keys, quota errors, and network
failures degrade into a structured error so the chat layer can fall back to
backend state.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TIMEOUT_SEC = 8.0
_DOTENV_LOADED = False


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    content: str
    published_date: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class WebSearchResult:
    query: str
    provider: str
    answer: str | None
    results: list[WebSearchHit]
    usage_credits: int | None = None
    error: str | None = None


def _load_repo_dotenv_once() -> None:
    """Load root .env for missing envs only; shell env still wins."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    load_flag = os.environ.get("TAVILY_LOAD_DOTENV", os.environ.get("LLM_LOAD_DOTENV", "true"))
    if load_flag.strip().lower() in {"0", "false", "no"}:
        return
    path = Path(__file__).resolve().parents[3] / ".env"
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


def _safe_int(value: str | None, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _clean_text(value: Any, *, limit: int = 420) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    return text[:limit].rstrip()


def search(
    query: str,
    *,
    topic: str = "news",
    time_range: str | None = "day",
    max_results: int | None = None,
) -> WebSearchResult:
    """Run a Tavily search and return bounded snippets.

    Returns ``error`` instead of raising. ``topic`` is limited to Tavily's public
    categories so callers cannot smuggle arbitrary request options through chat.
    """
    _load_repo_dotenv_once()
    q = query.strip()
    if not q:
        return WebSearchResult(q, "tavily", None, [], error="empty_query")

    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return WebSearchResult(q, "tavily", None, [], error="missing_api_key")

    depth = os.environ.get("TAVILY_SEARCH_DEPTH", "basic").strip().lower()
    if depth not in {"basic", "fast", "ultra-fast", "advanced"}:
        depth = "basic"
    selected_topic = topic if topic in {"general", "news", "finance"} else "news"
    selected_max = _safe_int(
        str(max_results) if max_results is not None else os.environ.get("TAVILY_MAX_RESULTS"),
        5,
        min_value=1,
        max_value=10,
    )
    selected_range = time_range if time_range in {"day", "week", "month", "year", "d", "w", "m", "y"} else None

    body: dict[str, Any] = {
        "query": q,
        "search_depth": depth,
        "topic": selected_topic,
        "max_results": selected_max,
        "include_answer": "basic",
        "include_raw_content": False,
        "include_images": False,
        "include_favicon": True,
        "include_usage": True,
    }
    if selected_range:
        body["time_range"] = selected_range

    req = urllib.request.Request(
        os.environ.get("TAVILY_SEARCH_URL", TAVILY_SEARCH_URL).strip() or TAVILY_SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "clean-e-yay/2.7",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return WebSearchResult(q, "tavily", None, [], error=f"http_{exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return WebSearchResult(q, "tavily", None, [], error="search_failed")

    hits: list[WebSearchHit] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"), limit=120)
        url = _clean_text(item.get("url"), limit=260)
        content = _clean_text(item.get("content"), limit=420)
        if not title or not url:
            continue
        score = item.get("score")
        hits.append(
            WebSearchHit(
                title=title,
                url=url,
                content=content,
                published_date=_clean_text(item.get("published_date"), limit=32) or None,
                score=float(score) if isinstance(score, (int, float)) else None,
            )
        )

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    credits = usage.get("credits") if isinstance(usage, dict) else None
    answer = _clean_text(data.get("answer"), limit=650) or None
    return WebSearchResult(
        q,
        "tavily",
        answer,
        hits,
        usage_credits=int(credits) if isinstance(credits, int) else None,
    )
