"""Contract tests for the user-provided technical-analysis knowledge corpus."""
from __future__ import annotations

import json

import pytest

from packages.knowledge import technical_analysis
from packages.knowledge.technical_analysis import decision_evidence_summary, search


@pytest.fixture(autouse=True)
def _fixture_corpus(tmp_path, monkeypatch):
    """Gercek korpus gitignored (data/knowledge); test kucuk sentetik korpusla kosar."""
    rows = [
        {
            "chunk_id": f"fixture_book:p{page:04d}:c00",
            "book_id": "fixture_book",
            "title": "Fixture",
            "source_page": page,
            "text": f"stop seviyesi ve trend yapisi ornek sayfa {page}",
            "topics": ["risk_stops", "trend_structure"],
            "quality": "ocr",
        }
        for page in (1, 2, 3, 4)
    ]
    corpus = tmp_path / "technical_analysis_books.jsonl"
    corpus.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("TECHNICAL_BOOK_CORPUS_PATH", str(corpus))
    technical_analysis._records.cache_clear()
    yield
    technical_analysis._records.cache_clear()


def test_corpus_is_traceable_and_bounded() -> None:
    cards = search(topics=("risk_stops",), limit=3)
    assert cards
    assert len(cards) <= 3
    assert all(card["source_page"] >= 1 for card in cards)
    assert all(card["book_id"] and card["chunk_id"] for card in cards)
    assert all(card["text"] for card in cards)


def test_decision_evidence_is_not_promoted() -> None:
    summary = decision_evidence_summary()
    assert summary["status"] == "READY"
    assert summary["mode"] == "evidence_only"
    assert summary["promoted_to_decision"] is False
    assert summary["references"]


def test_missing_corpus_is_unavailable_not_an_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TECHNICAL_BOOK_CORPUS_PATH", str(tmp_path / "yok.jsonl"))
    technical_analysis._records.cache_clear()
    summary = decision_evidence_summary()
    assert summary["status"] == "UNAVAILABLE"
    assert summary["references"] == []
    assert summary["promoted_to_decision"] is False
