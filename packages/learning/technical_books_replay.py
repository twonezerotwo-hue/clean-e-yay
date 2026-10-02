"""Evidence-calibrated replay for the technical-analysis book corpus.

This module joins the existing stored-snapshot replay with the technical evidence
present at each decision time.  It is deliberately a challenger report: it never
recomputes live decisions, writes paper state, changes weights, or opens trades.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from packages.data import backtest, snapshot_store
from packages.knowledge.technical_analysis import decision_evidence_summary

ALGO_VERSION = 1
MIN_TOPIC_SAMPLES = 30
_NO_EXECUTION = "no_live_execution"


def _technical_row(doc: dict, symbol: str, timeframe: str) -> dict[str, Any]:
    by_symbol = (doc.get("causal_reconstruction") or {}).get("technicals_by_tf") or {}
    return ((by_symbol.get(symbol) or {}).get(timeframe) or {})


def _topics(doc: dict, symbol: str, timeframe: str, cell: dict) -> tuple[str, ...]:
    """Map stored indicator evidence to corpus topics without inventing signals."""
    row = _technical_row(doc, symbol, timeframe)
    location = " ".join(str(item) for item in (row.get("location_evidence") or []))
    warnings = " ".join(str(item) for item in (cell.get("warnings") or []))
    text = f"{location} {warnings}".casefold()
    out: set[str] = set()
    if row.get("rsi") is not None or row.get("macd") is not None:
        out.add("indicators_momentum")
    if row.get("ema_stack"):
        out.add("moving_averages")
    if "fib" in text or "fibonacci" in text:
        out.add("fibonacci")
    if "support" in text or "resistance" in text or "destek" in text or "diren" in text:
        out.add("support_resistance")
    if "pattern" in text or "formasyon" in text:
        out.add("patterns")
    if "trend" in text or row.get("direction_score") is not None:
        out.add("trend_structure")
    return tuple(sorted(out)) or ("trend_structure",)


def _metric(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for row in rows if row["signed_return"] > 0)
    returns = [float(row["signed_return"]) for row in rows]
    return {
        "samples": n,
        "wins": wins,
        "hit_rate": round(wins / n, 4) if n else None,
        "avg_return_pct": round(sum(returns) / n * 100.0, 5) if n else None,
        "positive_edge": bool(n and sum(returns) / n > 0),
        "eligible_for_promotion": bool(n >= MIN_TOPIC_SAMPLES and n and sum(returns) / n > 0),
    }


def _run_id(docs: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(f"technical-books-v{ALGO_VERSION}".encode())
    for doc in docs:
        h.update(f"|{doc.get('snapshot_id')}@{doc.get('generated_at')}".encode())
    return h.hexdigest()[:16]


def run_replay() -> dict[str, Any]:
    """Return a deterministic baseline vs evidence-stratified replay report."""
    docs = snapshot_store.all_docs()
    docs_with_time: list[tuple[float, dict, dict[str, float]]] = []
    for doc in docs:
        epoch = backtest._epoch(doc.get("generated_at"))
        if epoch is not None:
            docs_with_time.append((epoch, doc, backtest._prices(doc)))
    docs_with_time.sort(key=lambda item: item[0])

    all_rows: list[dict] = []
    by_topic: dict[str, list[dict]] = {}
    by_topic_horizon: dict[tuple[str, str], list[dict]] = {}
    by_horizon: dict[str, list[dict]] = {}
    insufficient_future = Counter()
    candidate_setups = 0
    final_signals = 0

    for i, (epoch, doc, prices) in enumerate(docs_with_time):
        for cell in backtest._cells(doc):
            symbol = str(cell.get("symbol") or "")
            timeframe = str(cell.get("timeframe") or "")
            if not symbol or not timeframe:
                continue
            candidate_dir = backtest._dir(cell.get("candidate_action"))
            final_dir = backtest._dir(cell.get("action"))
            if candidate_dir == 0 and final_dir == 0:
                continue
            base_price = prices.get(symbol)
            if not base_price or base_price <= 0:
                continue
            candidate_setups += int(candidate_dir != 0)
            final_signals += int(final_dir != 0)
            directions = final_dir or candidate_dir
            topics = _topics(doc, symbol, timeframe, cell)
            for horizon, seconds in backtest.HORIZONS:
                future = backtest._future_price(docs_with_time, i, epoch + seconds, symbol)
                if future is None or future <= 0:
                    insufficient_future[horizon] += 1
                    continue
                signed_return = directions * ((future - base_price) / base_price)
                row = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "horizon": horizon,
                    "signed_return": signed_return,
                    "final_signal": bool(final_dir),
                    "topics": topics,
                }
                all_rows.append(row)
                by_horizon.setdefault(horizon, []).append(row)
                for topic in topics:
                    by_topic.setdefault(topic, []).append(row)
                    by_topic_horizon.setdefault((topic, horizon), []).append(row)

    topic_metrics = {}
    for topic in sorted(by_topic):
        topic_metrics[topic] = {
            "all_horizons": _metric(by_topic[topic]),
            "per_horizon": {
                horizon: _metric(by_topic_horizon[(topic, horizon)])
                for horizon, _ in backtest.HORIZONS
                if (topic, horizon) in by_topic_horizon
            },
        }

    summary = decision_evidence_summary(limit=4)
    eligible_topics = [topic for topic, value in topic_metrics.items() if value["all_horizons"]["eligible_for_promotion"]]
    return {
        "status": "ok" if docs else "insufficient_snapshots",
        "available": bool(docs),
        "run_id": _run_id(docs),
        "algo_version": ALGO_VERSION,
        "execution": _NO_EXECUTION,
        "mode": "shadow_only",
        "snapshot_count": len(docs),
        "usable_snapshot_count": len(docs_with_time),
        "candidate_setups": candidate_setups,
        "final_signals": final_signals,
        "outcomes_evaluated": len(all_rows),
        "baseline": _metric(all_rows),
        "baseline_by_horizon": {horizon: _metric(rows) for horizon, rows in by_horizon.items()},
        "book_evidence": {
            "dataset_id": summary["dataset_id"],
            "schema_version": summary["schema_version"],
            "corpus_records": summary["corpus_records"],
            "references": summary["references"],
        },
        "by_topic": topic_metrics,
        "coverage": {
            "insufficient_future_data": {
                "total": sum(insufficient_future.values()),
                "per_horizon": dict(insufficient_future),
            }
        },
        "promotion": {
            "status": "candidate" if eligible_topics else "insufficient_evidence",
            "eligible_topics": eligible_topics,
            "minimum_samples_per_topic": MIN_TOPIC_SAMPLES,
            "auto_apply": False,
            "reason": "Sonuç yalnızca topic-stratified shadow kanıtıdır; out-of-sample doğrulama ve risk incelemesi olmadan canlı ağırlık değişmez.",
        },
    }


__all__ = ["ALGO_VERSION", "MIN_TOPIC_SAMPLES", "run_replay"]
