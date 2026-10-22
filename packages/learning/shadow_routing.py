"""Birleşik gölge kanıtı ve karar-yolu öneri raporu.

Bu modül çok sayıdaki gölge artifact'ını tek, okunabilir bir kanıt yüzeyinde
birleştirir. Hiçbir öneriyi canlı karara, ağırlığa, RiskGate'e veya paper state'e
uygulamaz. Amaç iki ayrı soruyu ayırmaktır:

* Sinyal gerçekten aday giriş miydi?
* Aday giriş hangi kapı tarafından engellendi?

Rapor öğrenme worker'ında ucuz bir adım olarak üretilir; ağır backtestlerin yerine
geçmez ve onları tekrar çalıştırmaz.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

ENGINE = "shadow_routing_v1"
ROUTING_PATH = Path("data/runtime/shadow_routing.json")


def _routing_path() -> Path:
    """Resolve the runtime artifact path without capturing test env at import time."""
    configured = os.getenv("SHADOW_ROUTING_PATH")
    return Path(configured) if configured else ROUTING_PATH


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _counterfactual_summary() -> dict[str, Any]:
    """Son shadow kayıtlarından aday/final ayrımını toplar.

    Eski kayıtlarda candidate telemetrisi yoksa satır sessizce atlanır; geçmiş
    kayıtlar için uydurma değer üretmeyiz.
    """
    try:
        from packages.decision import shadow

        records = shadow.read_recent(limit=200)
    except Exception:
        records = []

    blocked: Counter[str] = Counter()
    snapshots = 0
    symbols = 0
    candidate_cells = 0
    blocked_symbols = 0
    for record in records:
        snapshots += 1
        top = record.get("candidate_summary") or {}
        if top:
            symbols += int(top.get("symbols_with_candidate") or 0)
            candidate_cells += int(top.get("candidate_entry_cells") or 0)
            blocked_symbols += int(top.get("candidate_not_actionable_symbols") or 0)
            blocked.update({str(k): int(v) for k, v in (top.get("blocked_by") or {}).items()})
            continue
        for row in record.get("symbols") or []:
            live = row.get("live") or {}
            cells = int(live.get("candidate_entry_cells") or 0)
            if not cells:
                continue
            symbols += 1
            candidate_cells += cells
            if not live.get("wants_entry"):
                blocked_symbols += 1
            blocked.update(str(x) for x in (live.get("candidate_blocked_by") or []))

    return {
        "snapshots": snapshots,
        "symbols_with_candidate": symbols,
        "candidate_entry_cells": candidate_cells,
        "candidate_not_actionable_symbols": blocked_symbols,
        "blocked_by": dict(blocked.most_common(20)),
        "measurement": "candidate_action_vs_final_action",
    }


def _asset_evidence() -> dict[str, Any]:
    try:
        from packages.discovery import promotion, shadow_ledger

        summary = shadow_ledger.candidate_summary()
        candidates = dict(summary.get("candidates") or {})
        evaluation = promotion.evaluate(candidates=candidates)
        per = evaluation.get("per_candidate") or {}
        rows = []
        for symbol, data in candidates.items():
            ev = per.get(symbol) or {}
            rows.append(
                {
                    "symbol": symbol,
                    "resolved": int(data.get("resolved") or 0),
                    "cf_win_rate": data.get("cf_win_rate"),
                    "avg_r": data.get("avg_r"),
                    "timeframes": list(data.get("timeframes") or []),
                    "promotion_status": ev.get("status", "NOT_READY"),
                    "checks": ev.get("checks") or {},
                }
            )
        rows.sort(
            key=lambda r: (
                r["promotion_status"] != "READY",
                -(float(r["avg_r"]) if r["avg_r"] is not None else -999.0),
                -r["resolved"],
            )
        )
        return {
            "status": evaluation.get("status", "NOT_READY"),
            "ready_symbols": list(evaluation.get("ready_symbols") or []),
            "candidates": rows[:25],
            "shadow_only": True,
        }
    except Exception as exc:  # artifact raporu worker'ı düşürmez
        return {"status": "ERROR", "error": type(exc).__name__, "candidates": [], "shadow_only": True}


def _news_evidence() -> dict[str, Any]:
    try:
        from packages.discovery import news_decision_shadow

        return {**news_decision_shadow.scorecard(), "shadow_only": True}
    except Exception as exc:
        return {"status": "ERROR", "error": type(exc).__name__, "shadow_only": True}


def _artifact(name: str) -> dict[str, Any]:
    return _read_json(Path("data/runtime") / name)


def _recommendations(
    performance: dict[str, Any],
    assets: dict[str, Any],
    news: dict[str, Any],
    race: dict[str, Any],
    exit_report: dict[str, Any],
    council: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn shadow evidence into reviewable, non-activating next steps.

    These are deliberately review items, not feature flags. A recommendation can
    be promoted only by a separate owner-approved canary change.
    """
    out: list[dict[str, Any]] = []
    close = performance.get("by_close_reason") or {}
    sl = close.get("SL_HIT") or {}
    if int(sl.get("trades") or 0) >= 20 and float(sl.get("total_pnl") or 0) < 0:
        out.append(
            {
                "id": "exit-sl-review",
                "priority": "HIGH",
                "shadow": "exit_backtest",
                "finding": "SL_HIT is the largest negative close bucket",
                "evidence": sl,
                "next_step": "Run per-timeframe exit canary; do not change live exits yet",
                "activation": "OWNER_APPROVAL_REQUIRED",
            }
        )
    # Zamanlama teşhisi: yalnızca yeterli örnek + negatif ortalama R varsa
    # review üret. Bu bir canlı kapı değildir; 4h/1d gibi yüksek TF'leri körce
    # kapatmadan önce temiz holdout kanıtı ister.
    by_tf = performance.get("by_timeframe") or {}
    weak_tf = [
        tf for tf, row in by_tf.items()
        if int(row.get("trades") or 0) >= 20
        and float(row.get("avg_r") or 0.0) < 0.0
    ]
    if weak_tf:
        out.append(
            {
                "id": "entry-timing-review",
                "priority": "HIGH",
                "shadow": "learning_summary",
                "finding": "Bazı zaman dilimleri temiz performansta negatif R üretiyor",
                "evidence": {"timeframes": weak_tf},
                "next_step": "Zaman dilimi başına giriş/stop kanaryası; canlı eşik değişikliği yapma",
                "activation": "OWNER_APPROVAL_REQUIRED",
            }
        )
    if race.get("beats_backup"):
        out.append(
            {
                "id": "technical-v4-canary",
                "priority": "MEDIUM",
                "shadow": "tf_scoring_race",
                "finding": "V4 beats the backup in replay",
                "evidence": {
                    "race_status": race.get("race_status"),
                    "beats_backup": race.get("beats_backup"),
                    "beats_baseline": race.get("beats_baseline"),
                },
                "next_step": "Keep V4 as shadow canary and collect out-of-sample evidence",
                "activation": "SHADOW_ONLY",
            }
        )
    if not assets.get("ready_symbols"):
        out.append(
            {
                "id": "asset-promotion-blocked",
                "priority": "HIGH",
                "shadow": "asset_discovery",
                "finding": "No discovered asset satisfies promotion evidence and price-source checks",
                "evidence": {"candidate_count": len(assets.get("candidates") or [])},
                "next_step": "Keep candidates in shadow; add a mapped price source before review",
                "activation": "OWNER_APPROVAL_REQUIRED",
            }
        )
    if news and news.get("resolved_total"):
        out.append(
            {
                "id": "news-confirmation-only",
                "priority": "MEDIUM",
                "shadow": "news_decision_shadow",
                "finding": "News relation is informative but not yet causal proof",
                "evidence": {"resolved_total": news.get("resolved_total")},
                "next_step": "Use news as confirmation evidence; keep decision action unchanged",
                "activation": "SHADOW_ONLY",
            }
        )
    what_if = council.get("what_if") or []
    if what_if:
        best = max(what_if, key=lambda row: float(row.get("avg_r") or -999.0))
        out.append(
            {
                "id": "council-filter-review",
                "priority": "MEDIUM",
                "shadow": "council_scorecard",
                "finding": "The best replay filter is not yet a live rule",
                "evidence": best,
                "next_step": "Validate the filter on a fresh holdout before any canary",
                "activation": "OWNER_APPROVAL_REQUIRED",
            }
        )
    return out


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    learning = _artifact("learning_summary.json")
    exit_report = _artifact("exit_backtest.json")
    race = _artifact("tf_scoring_race_report.json")
    council = _artifact("council_scorecard.json")
    paper_canary = _artifact("paper_canary.json")
    entry_exit = paper_canary.get("timing_canary", {}).get("entry_exit_quality") or {}
    news = _news_evidence()
    assets = _asset_evidence()
    from packages.learning import shadow_policy

    race_status = race.get("race_status")
    # Premium rapor temiz, öğrenilebilir kohortu esas alır. Ham metrikler
    # learning_summary içindeki eski alanlarda korunur; anomaliler/legacy
    # yüzünden karar kalitesi olduğundan iyi veya kötü gösterilmez.
    clean = learning.get("performance") or {}
    performance = {
        "total_trades": clean.get("total_trades", learning.get("total_trades", 0)),
        "win_rate": clean.get("win_rate", learning.get("win_rate")),
        "expectancy_r": clean.get("expectancy_r", learning.get("expectancy_r")),
        "total_pnl": clean.get("total_pnl"),
        "excluded_from_learning": clean.get("excluded_from_learning", 0),
        "provenance_incomplete": clean.get("provenance_incomplete", 0),
        "execution_anomalies": clean.get("execution_anomalies", 0),
        "by_close_reason": {
            key: {
                "trades": value.get("trades", 0),
                "win_rate": value.get("win_rate"),
                "total_pnl": value.get("total_pnl"),
            }
            for key, value in (learning.get("by_close_reason") or {}).items()
        },
        "by_timeframe": clean.get("by_timeframe") or learning.get("by_timeframe") or {},
    }
    return {
        "generated_at": now.isoformat(),
        "engine": ENGINE,
        "shadow_only": True,
        "live_decision_changed": False,
        "paper_safe": True,
        "no_execution": True,
        "performance": performance,
        "counterfactual": _counterfactual_summary(),
        "asset_discovery": assets,
        "news_decision": news,
        "technical_race": {
            "status": race_status or "NO_DATA",
            "beats_backup": race.get("beats_backup"),
            "beats_baseline": race.get("beats_baseline"),
            "recommendation": (
                "V4_PRIMARY_SHADOW_CANARY" if race.get("beats_backup") else "KEEP_OBSERVING"
            ),
        },
        "exit_canary": {
            "status": "SHADOW_ONLY",
            "per_timeframe": exit_report.get("per_tf_best") or {},
            "best_config": (exit_report.get("best_configs") or [None])[0],
        },
        "entry_exit_quality": {
            "status": "SHADOW_ONLY",
            "flagged_count": entry_exit.get("flagged_count", 0),
            "verdict_counts": entry_exit.get("verdict_counts") or {},
            "buckets": entry_exit.get("buckets") or [],
        },
        "paper_canary": paper_canary or {
            "status": "NO_DATA",
            "shadow_only": True,
            "paper_safe": True,
            "no_execution": True,
        },
        "council": {
            "status": council.get("status", "NO_DATA"),
            "shadow_only": True,
            "what_if": council.get("what_if") or [],
        },
        "recommendations": _recommendations(
            performance, assets, news, race, exit_report, council
        ),
        "routing": {
            "counterfactual": "MEASURE_BEFORE_GATE_TUNING",
            "news": "CONFIRMATION_ONLY",
            "asset_discovery": "PROMOTION_REQUIRES_OWNER_AND_PRICE_SOURCE",
            "exit": "PER_TIMEFRAME_CANARY_ONLY",
            "automatic_activation": False,
        },
        "policy": shadow_policy.evaluate(),
    }


def run(now: datetime | None = None) -> dict[str, Any]:
    report = build_report(now)
    try:
        path = _routing_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(report, ensure_ascii=False, indent=2))
    except OSError:
        return {"status": "ERROR", "engine": ENGINE}
    return {
        "status": "OK",
        "engine": ENGINE,
        "candidates": len((report.get("asset_discovery") or {}).get("candidates") or []),
        "candidate_cells": (report.get("counterfactual") or {}).get("candidate_entry_cells", 0),
    }


def viewmodel() -> dict[str, Any]:
    report = _read_json(_routing_path())
    if not report:
        return {
            "status": "NO_DATA",
            "shadow_only": True,
            "live_decision_changed": False,
            "paper_safe": True,
            "no_execution": True,
        }
    return report


__all__ = ["build_report", "run", "viewmodel"]
