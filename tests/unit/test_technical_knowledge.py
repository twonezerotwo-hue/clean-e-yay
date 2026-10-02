"""Contract tests for the user-provided technical-analysis knowledge corpus."""
from __future__ import annotations

from packages.knowledge.technical_analysis import decision_evidence_summary, search


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
