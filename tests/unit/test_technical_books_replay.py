"""Outcome-labelled, book-evidence replay stays shadow-only."""
from __future__ import annotations

import json

import pytest

from packages.knowledge import technical_analysis
from packages.learning import technical_books_replay as replay


@pytest.fixture(autouse=True)
def _fixture_corpus(tmp_path, monkeypatch):
    """Gercek korpus gitignored (data/knowledge); test kucuk sentetik korpusla kosar."""
    row = {
        "chunk_id": "fixture_book:p0001:c00",
        "book_id": "fixture_book",
        "source_page": 1,
        "text": "trend yapisi ornek sayfa",
        "topics": ["trend_structure"],
        "quality": "ocr",
    }
    corpus = tmp_path / "technical_analysis_books.jsonl"
    corpus.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setenv("TECHNICAL_BOOK_CORPUS_PATH", str(corpus))
    technical_analysis._records.cache_clear()
    yield
    technical_analysis._records.cache_clear()


def _snapshot(ts: str, price: float, *, action: str, candidate: str) -> dict:
    return {
        "snapshot_id": f"snap-{ts}",
        "generated_at": ts,
        "data_snapshot": {"prices": [{"symbol": "BTCUSD", "price": price}]},
        "causal_reconstruction": {
            "technicals_by_tf": {
                "BTCUSD": {
                    "1h": {
                        "rsi": 62.0,
                        "macd": 0.2,
                        "ema_stack": "bullish",
                        "direction_score": 75.0,
                        "location_evidence": ["fib_zone=near_support", "pattern=uptrend_structure"],
                    }
                }
            }
        },
        "decision_matrix": {
            "cells": [
                {
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                    "action": action,
                    "candidate_action": candidate,
                    "warnings": [],
                }
            ]
        },
    }


def test_replay_labels_future_price_and_keeps_promotion_shadow(monkeypatch) -> None:
    docs = [
        _snapshot("2026-01-01T00:00:00+00:00", 100.0, action="hold", candidate="open_long"),
        _snapshot("2026-01-02T00:00:00+00:00", 110.0, action="hold", candidate="hold"),
    ]
    monkeypatch.setattr(replay.snapshot_store, "all_docs", lambda: docs)

    result = replay.run_replay()

    assert result["status"] == "ok"
    assert result["outcomes_evaluated"] > 0
    assert result["baseline"]["hit_rate"] == 1.0
    assert result["promotion"]["auto_apply"] is False
    assert result["promotion"]["status"] == "insufficient_evidence"
    assert "indicators_momentum" in result["by_topic"]
    assert result["book_evidence"]["corpus_records"] > 0
