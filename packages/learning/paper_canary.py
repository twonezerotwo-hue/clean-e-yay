"""Kanıt-kapılı paper kanaryası (salt-gözlem).

Bu modül altı ayrı gölge ölçümünü tek bir owner inceleme yüzeyinde birleştirir:
giriş/stop zamanlaması, 1 saatlik negatif performans teşhisi, haber kaynak
konsensüsü, fiyat sağlayıcısı ve teknik teyit, rejim ağırlığı what-if testi ve
holdout yarış karnesi. Hiçbir emir açmaz, paper state'i değiştirmez ve canlı
skor/weight/RiskGate akışına bağlanmaz.

``PAPER_CANARY_PENDING_OWNER`` yalnız bütün kanıt kapıları geçince üretilen bir
öneridir; otomatik aktivasyon yoktur. Kanıt eksikse aday ``WAITING_EVIDENCE``
olarak kalır. Böylece öğrenme kanıtı oluşmadan yeni bir davranış üretilemez.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

ENGINE = "paper_canary_v1"
CANARY_PATH = Path("data/runtime/paper_canary.json")

# Bu eşikler raporun anlamını sabit tutar. Hiçbiri canlı karar eşiği değildir.
MIN_TF_TRADES = 20
MIN_NEWS_FAMILIES = 2
MIN_RACE_RESOLVED = 30
SUPPORTED_TECHNICAL = {"WOULD_OPEN_LONG", "WOULD_OPEN_SHORT"}


def _path() -> Path:
    configured = os.environ.get("PAPER_CANARY_PATH")
    return Path(configured) if configured else CANARY_PATH


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _artifact(name: str) -> dict[str, Any]:
    return _read_json(Path("data/runtime") / name)


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _perf(learning: Mapping[str, Any]) -> dict[str, Any]:
    # Premium temiz kohort önceliklidir; yoksa eski summary okunur.
    return dict(learning.get("performance") or {
        "total_trades": learning.get("total_trades", 0),
        "win_rate": learning.get("win_rate"),
        "expectancy_r": learning.get("expectancy_r"),
        "by_timeframe": learning.get("by_timeframe") or {},
    })


def _load_ideas() -> list[dict[str, Any]]:
    try:
        from packages.discovery import ideas

        return [dict(row) for row in (ideas.viewmodel().get("ideas") or []) if isinstance(row, Mapping)]
    except Exception:
        return []


def _load_entry_report() -> dict[str, Any]:
    try:
        from packages.learning import entry_exit_quality

        return entry_exit_quality.report()
    except Exception as exc:
        return {"status": "ERROR", "error": type(exc).__name__, "buckets": []}


def _load_forecasts() -> dict[str, dict[str, Any]]:
    try:
        from packages.discovery import news_forecast

        return {
            str(symbol): dict(value)
            for symbol, value in news_forecast.load_forecasts().items()
            if isinstance(value, Mapping)
        }
    except Exception:
        return {}


def _timing_gate(
    timeframe: str | None,
    performance: Mapping[str, Any],
    exit_report: Mapping[str, Any],
) -> dict[str, Any]:
    by_tf = performance.get("by_timeframe") or {}
    row = dict(by_tf.get(timeframe or "") or {})
    trades = int(row.get("trades") or 0)
    avg_r = _num(row.get("avg_r"))
    reasons: list[str] = []
    if trades < MIN_TF_TRADES:
        reasons.append("timeframe_sample_insufficient")
    if avg_r is None or avg_r < 0:
        reasons.append("timeframe_negative_expectancy")

    exit_by_tf = dict(exit_report.get("per_tf_best") or {})
    exit_row = dict(exit_by_tf.get(timeframe or "") or {})
    exit_avg = _num(exit_row.get("avg_r"))
    if exit_row and (exit_avg is None or exit_avg < 0):
        reasons.append("exit_canary_negative")
    return {
        "pass": not reasons,
        "status": "READY" if not reasons else "REVIEW_REQUIRED",
        "timeframe": timeframe,
        "evidence": {
            "clean_trades": trades,
            "min_required": MIN_TF_TRADES,
            "clean_avg_r": avg_r,
            "exit_canary_avg_r": exit_avg,
        },
        "blocked_by": reasons,
        "scope": "entry_stop_timing_shadow_only",
    }


def _one_hour_analysis(performance: Mapping[str, Any], entry_report: Mapping[str, Any]) -> dict[str, Any]:
    by_tf = performance.get("by_timeframe") or {}
    row = dict(by_tf.get("1h") or {})
    verdicts: list[dict[str, Any]] = []
    for bucket in entry_report.get("buckets") or []:
        if str(bucket.get("timeframe") or "") != "1h":
            continue
        for verdict in bucket.get("verdicts") or []:
            verdicts.append({
                "module": bucket.get("module"),
                "code": verdict.get("code"),
                "detail": verdict.get("detail"),
            })
    avg_r = _num(row.get("avg_r"))
    status = "REVIEW_REQUIRED" if avg_r is None or avg_r < 0 else "NO_NEGATIVE_EVIDENCE"
    return {
        "status": status,
        "trades": int(row.get("trades") or 0),
        "win_rate": row.get("win_rate"),
        "avg_r": avg_r,
        "total_pnl": row.get("total_pnl"),
        "diagnoses": verdicts,
        "recommendation": (
            "Giriş ve stop zamanlamasını 1h için gölgede ayrı ölç; canlı eşiği değiştirme."
            if status == "REVIEW_REQUIRED" else "1h için negatif kanıt yok; izlemeye devam et."
        ),
        "shadow_only": True,
    }


def _timeframe_canary(
    performance: Mapping[str, Any], exit_report: Mapping[str, Any]
) -> dict[str, Any]:
    """Expose the 1h/4h entry+stop shadow gates as one stable artifact.

    This is deliberately report-only: it does not alter the live timeframe
    weights, RiskGate, or paper opener.  Keeping both horizons next to each
    other prevents a single aggregate score from hiding a weak timeframe.
    """
    return {
        timeframe: _timing_gate(timeframe, performance, exit_report)
        for timeframe in ("1h", "4h")
    }


def _news_gate(idea: Mapping[str, Any], forecasts: Mapping[str, Any]) -> dict[str, Any]:
    news = dict(idea.get("news") or {})
    if not news:
        news = dict(forecasts.get(str(idea.get("symbol") or "")) or {})
    families = int(news.get("independent_source_families") or 0)
    direction = str(news.get("direction") or "neutral")
    technical = str((idea.get("technical") or {}).get("verdict") or "")
    wanted = "up" if technical == "WOULD_OPEN_LONG" else "down" if technical == "WOULD_OPEN_SHORT" else "neutral"
    reasons: list[str] = []
    if str(news.get("evidence_status") or "") != "CONFIRMED":
        reasons.append("news_consensus_not_confirmed")
    if families < MIN_NEWS_FAMILIES:
        reasons.append("independent_source_families_insufficient")
    if bool(news.get("conflict")) or direction == "neutral":
        reasons.append("news_direction_conflict_or_neutral")
    if wanted != "neutral" and direction != wanted:
        reasons.append("news_technical_direction_mismatch")
    return {
        "pass": not reasons,
        "status": "READY" if not reasons else "WAITING_EVIDENCE",
        "evidence": {
            "status": news.get("evidence_status"),
            "direction": direction,
            "technical_direction": wanted,
            "independent_source_families": families,
            "source_families": list(news.get("source_families") or []),
            "stories": int(news.get("n_stories") or 0),
        },
        "blocked_by": reasons,
        "scope": "news_confirmation_only",
    }


def _source_gate(idea: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(idea.get("source") or {})
    technical = dict(idea.get("technical") or {})
    provider = source.get("provider")
    # A scanner observation may be hours old (or absent).  Only the current
    # quote from the canonical provider can satisfy the paper pre-check.
    price = _num(source.get("current_price"))
    reasons: list[str] = []
    if not source.get("mapped_for_paper") or not provider:
        reasons.append("paper_price_provider_unmapped")
    if price is None or price <= 0:
        reasons.append("current_discovery_price_missing")
    if not bool(source.get("current_price_verified")):
        reasons.append("current_discovery_price_unverified")
    return {
        "pass": not reasons,
        "status": "READY" if not reasons else "WAITING_EVIDENCE",
        "evidence": {"provider": provider, "provider_id": source.get("provider_id"), "price": price,
                     "mapped_for_paper": bool(source.get("mapped_for_paper")),
                     "current_price_verified": bool(source.get("current_price_verified")),
                     "discovery_price": _num(source.get("discovery_price")),
                     "technical_entry": _num(technical.get("entry"))},
        "blocked_by": reasons,
        "scope": "price_source_required",
    }


def _technical_gate(idea: Mapping[str, Any]) -> dict[str, Any]:
    technical = dict(idea.get("technical") or {})
    verdict = str(technical.get("verdict") or "")
    tf = technical.get("entry_timeframe")
    confidence = _num(technical.get("confidence"))
    expected = _num(technical.get("expected_value"))
    ta = dict(technical.get("ta") or {})
    reasons: list[str] = []
    if verdict not in SUPPORTED_TECHNICAL:
        reasons.append("technical_verdict_not_actionable")
    if not tf:
        reasons.append("technical_timeframe_missing")
    if confidence is None or confidence <= 0:
        reasons.append("technical_confidence_missing")
    if expected is None or expected < 0:
        reasons.append("technical_expected_value_negative_or_missing")
    if not ta.get("bias"):
        reasons.append("technical_confirmation_missing")
    if not list(ta.get("confirmations") or []):
        reasons.append("technical_indicator_confirmation_missing")
    return {
        "pass": not reasons,
        "status": "READY" if not reasons else "WAITING_EVIDENCE",
        "evidence": {"verdict": verdict, "timeframe": tf, "confidence": confidence,
                     "expected_value": expected, "bias": ta.get("bias"),
                     "confirmations": list(ta.get("confirmations") or [])},
        "blocked_by": reasons,
        "scope": "technical_confirmation_required",
    }


def _regime_weight_test(learning: Mapping[str, Any], regime_report: Mapping[str, Any]) -> dict[str, Any]:
    quality = dict(learning.get("signal_quality") or {})
    overall = dict(quality.get("overall") or {})
    inverse = sorted(module for module, row in overall.items()
                     if str((row or {}).get("verdict") or "").upper() in {"INVERSE", "INSUFFICIENT"})
    regimes = dict(quality.get("per_regime") or {})
    return {
        "status": "HOLD" if inverse else "SHADOW_READY",
        "inverse_or_insufficient_modules": inverse,
        "per_regime": regimes,
        "risk_brake": {
            "braked_regimes": list(regime_report.get("braked_regimes") or []),
        },
        "weight_changes": [],
        "recommendation": "Ağırlık değiştirme; inverse/insufficient kanıtı temiz holdout ile çözülene kadar gölgede tut."
        if inverse else "Ağırlık değişikliği yok; rejim bazlı ileri kanıt biriktir.",
        "shadow_only": True,
    }


def _race_gate(race: Mapping[str, Any]) -> dict[str, Any]:
    checks = dict(race.get("checks") or {})
    resolved = int(race.get("resolved") or 0)
    ci_pass = bool((checks.get("ci_disjoint") or {}).get("pass"))
    passed = bool(race.get("beats_baseline")) and ci_pass and resolved >= MIN_RACE_RESOLVED
    reasons = []
    if resolved < MIN_RACE_RESOLVED:
        reasons.append("holdout_sample_insufficient")
    if not race.get("beats_baseline"):
        reasons.append("technical_race_does_not_beat_baseline")
    if not ci_pass:
        reasons.append("race_confidence_interval_not_passed")
    return {
        "pass": passed,
        "status": "READY" if passed else "WAITING_EVIDENCE",
        "evidence": {"race_status": race.get("race_status"), "resolved": resolved,
                     "beats_backup": race.get("beats_backup"), "beats_baseline": race.get("beats_baseline"),
                     "ci_disjoint_pass": ci_pass},
        "blocked_by": reasons,
        "scope": "technical_holdout_only",
    }


def _news_consensus(forecasts: Mapping[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    families: Counter[str] = Counter()
    conflicts = 0
    for row in forecasts.values():
        status = str(row.get("evidence_status") or "NO_DATA")
        counts[status] += 1
        if row.get("conflict"):
            conflicts += 1
        for family in row.get("source_families") or []:
            families[str(family)] += 1
    return {
        "forecasts": len(forecasts),
        "by_evidence_status": dict(counts),
        "conflicts": conflicts,
        "source_families": dict(families),
        "min_independent_source_families": MIN_NEWS_FAMILIES,
        "decision_effect": "CONFIRMATION_ONLY",
        "shadow_only": True,
    }


def build_report(
    now: datetime | None = None,
    *,
    learning: Mapping[str, Any] | None = None,
    entry_report: Mapping[str, Any] | None = None,
    exit_report: Mapping[str, Any] | None = None,
    race: Mapping[str, Any] | None = None,
    ideas: list[Mapping[str, Any]] | None = None,
    forecasts: Mapping[str, Any] | None = None,
    regime_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    learning = learning if learning is not None else _artifact("learning_summary.json")
    entry_report = entry_report if entry_report is not None else _load_entry_report()
    exit_report = exit_report if exit_report is not None else _artifact("exit_backtest.json")
    race = race if race is not None else _artifact("tf_scoring_race_report.json")
    ideas = ideas if ideas is not None else _load_ideas()
    forecasts = forecasts if forecasts is not None else _load_forecasts()
    regime_report = regime_report if regime_report is not None else _artifact("regime_risk_brake.json")
    performance = _perf(learning)
    regime_test = _regime_weight_test(learning, regime_report)
    candidates: list[dict[str, Any]] = []
    for raw in ideas:
        idea = dict(raw)
        technical = dict(idea.get("technical") or {})
        timing = _timing_gate(technical.get("entry_timeframe"), performance, exit_report)
        news = _news_gate(idea, forecasts)
        source = _source_gate(idea)
        tech = _technical_gate(idea)
        race_gate = _race_gate(race)
        regime_gate = {
            "pass": regime_test.get("status") == "SHADOW_READY",
            "status": regime_test.get("status"),
            "evidence": {
                "inverse_or_insufficient_modules": regime_test.get("inverse_or_insufficient_modules") or [],
            },
            "blocked_by": (["regime_weight_evidence_hold"]
                           if regime_test.get("status") != "SHADOW_READY" else []),
            "scope": "regime_weight_shadow_only",
        }
        gates = {"timing": timing, "news_consensus": news, "asset_price_source": source,
                 "technical_confirmation": tech, "regime_weight_test": regime_gate, "holdout": race_gate}
        blocked = [f"{name}:{code}" for name, gate in gates.items() for code in gate.get("blocked_by") or []]
        all_pass = not blocked
        candidates.append({
            "symbol": idea.get("symbol"),
            "name": idea.get("name"),
            "direction": "LONG" if technical.get("verdict") == "WOULD_OPEN_LONG" else "SHORT" if technical.get("verdict") == "WOULD_OPEN_SHORT" else "UNKNOWN",
            "timeframe": technical.get("entry_timeframe"),
            "idea_score": idea.get("score"),
            "status": "PAPER_CANARY_PENDING_OWNER" if all_pass else "WAITING_EVIDENCE",
            "owner_approval_required": True,
            "automatic_activation": False,
            "blocked_by": blocked,
            "gates": gates,
        })
    pending = sum(row["status"] == "PAPER_CANARY_PENDING_OWNER" for row in candidates)
    report = {
        "generated_at": now.isoformat(),
        "engine": ENGINE,
        "status": "PAPER_CANARY_PENDING_OWNER" if pending else "WAITING_EVIDENCE",
        "shadow_only": True,
        "paper_safe": True,
        "no_execution": True,
        "owner_approval_required": True,
        "automatic_activation": False,
        "timing_canary": {
            "status": "SHADOW_ONLY",
            "entry_exit_quality": dict(entry_report),
            "exit_backtest": {"per_timeframe": exit_report.get("per_tf_best") or {},
                               "best_config": (exit_report.get("best_configs") or [None])[0],
                               "activation": "SHADOW_ONLY"},
        },
        "timeframe_canary": _timeframe_canary(performance, exit_report),
        "one_hour_analysis": _one_hour_analysis(performance, entry_report),
        "news_consensus": _news_consensus(forecasts),
        "asset_readiness": {
            "total": len(candidates),
            "price_source_ready": sum(bool(row["gates"]["asset_price_source"]["pass"]) for row in candidates),
            "technical_ready": sum(bool(row["gates"]["technical_confirmation"]["pass"]) for row in candidates),
            "news_consensus_ready": sum(bool(row["gates"]["news_consensus"]["pass"]) for row in candidates),
        },
        "regime_weight_test": regime_test,
        "holdout": _race_gate(race),
        "candidates": candidates,
        "counts": {"candidates": len(candidates), "pending_owner": pending,
                   "waiting_evidence": len(candidates) - pending},
        "policy": "Kanıt kapıları geçmeden paper kanaryası önerilmez; bu artifact hiçbir zaman emir açmaz.",
    }
    return report


def run(now: datetime | None = None, **kwargs: Any) -> dict[str, Any]:
    report = build_report(now, **kwargs)
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(report, ensure_ascii=False, indent=2))
    except OSError:
        return {"status": "ERROR", "engine": ENGINE}
    return {"status": "OK", "engine": ENGINE, **report.get("counts", {})}


def viewmodel() -> dict[str, Any]:
    report = _read_json(_path())
    return report or {"status": "NO_DATA", "engine": ENGINE, "shadow_only": True,
                      "paper_safe": True, "no_execution": True}


__all__ = ["build_report", "run", "viewmodel"]
