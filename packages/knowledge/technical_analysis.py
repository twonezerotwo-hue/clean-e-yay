"""Portable technical-analysis book corpus access.

The corpus is deliberately retrieval-only.  It can explain or trace a technical
observation, but it cannot alter a decision, bypass RiskGate, or increase size.
This boundary keeps literary guidance separate from outcome-calibrated strategy
weights until a labelled replay promotes a rule.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _ROOT / "data" / "knowledge" / "technical_analysis_books.jsonl"
_DEFAULT_MANIFEST = _ROOT / "data" / "knowledge" / "technical_analysis_books_manifest.json"
_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def corpus_path() -> Path:
    """Return the configured corpus path without creating or mutating state."""
    configured = os.getenv("TECHNICAL_BOOK_CORPUS_PATH")
    return Path(configured) if configured else _DEFAULT_CORPUS


@lru_cache(maxsize=1)
def _records() -> tuple[dict[str, Any], ...]:
    path = corpus_path()
    if not path.is_file():
        return ()
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("text") and row.get("quality") != "empty":
                    rows.append(row)
    return tuple(rows)


@lru_cache(maxsize=1)
def _manifest() -> dict[str, Any]:
    if not _DEFAULT_MANIFEST.is_file():
        return {}
    try:
        return json.loads(_DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in _TOKEN_RE.findall(value or "") if len(item) > 1}


def search(
    query: str = "",
    *,
    topics: Iterable[str] = (),
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return deterministic, page-traceable evidence cards from the corpus.

    Search is intentionally lexical and bounded.  It is not a model retraining
    step and its result must remain explanatory evidence in callers.
    """
    limit = max(0, min(int(limit), 20))
    if limit == 0:
        return []
    query_tokens = _tokens(query)
    wanted_topics = {str(topic) for topic in topics if topic}
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for row in _records():
        row_topics = set(row.get("topics") or [])
        topic_score = len(wanted_topics & row_topics)
        text_tokens = _tokens(row.get("text", ""))
        token_score = len(query_tokens & text_tokens)
        if wanted_topics and topic_score == 0 and not query_tokens:
            continue
        if query_tokens and token_score == 0 and topic_score == 0:
            continue
        # Topic match is stronger than a generic word match.  Earlier pages win
        # ties so the result is stable across processes and replay runs.
        score = topic_score * 10.0 + token_score
        scored.append((score, int(row.get("source_page", 0)), row))
    scored.sort(key=lambda item: (-item[0], item[1], item[2].get("chunk_id", "")))
    result: list[dict[str, Any]] = []
    for score, _, row in scored[:limit]:
        result.append(
            {
                "chunk_id": row.get("chunk_id"),
                "book_id": row.get("book_id"),
                "title": row.get("title"),
                "source_page": row.get("source_page"),
                "topics": row.get("topics", []),
                "quality": row.get("quality"),
                "score": round(score, 4),
                "text": row.get("text", ""),
            }
        )
    return result


def evidence_summary(
    *,
    topics: Iterable[str] = (),
    query: str = "",
    limit: int = 4,
) -> dict[str, Any]:
    """Build an additive read-only evidence summary for API/view-model callers."""
    topic_list = tuple(str(topic) for topic in topics if topic)
    manifest = _manifest()
    records = _records()
    refs = search(query, topics=topic_list, limit=limit)
    return {
        "status": "READY" if records else "UNAVAILABLE",
        "mode": "evidence_only",
        "dataset_id": manifest.get("dataset_id", "e-yay-technical-analysis-books"),
        "schema_version": manifest.get("schema_version", "technical_books.v1"),
        "corpus_records": len(records),
        "topics": list(dict.fromkeys(topic_list)),
        "references": refs,
        "promoted_to_decision": False,
    }


def decision_evidence_summary(*, limit: int = 4) -> dict[str, Any]:
    """Evidence bundle used by the additive decision view.

    Topic vocabulary lives here so the decision package remains independent of
    the corpus taxonomy and architecture guards can keep literary evidence out
    of the action/risk modules.
    """
    return evidence_summary(
        topics=(
            "trend_structure",
            "support_resistance",
            "indicators_momentum",
            "moving_averages",
            "volatility_bands",
            "fibonacci",
            "elliott_wave",
            "risk_stops",
        ),
        limit=limit,
    )
