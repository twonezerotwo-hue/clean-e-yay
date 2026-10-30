"""Evidence-gated performance readiness for the paper-safe learning loop.

This is a reporting gate, not a trading gate.  It deliberately scores the
clean learning cohort and keeps incomplete provenance visible so a high score
cannot be manufactured by mixing legacy or anomalous outcomes into the edge.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Promotion/readiness must not be declared from a small sample.  The 90-day
# forward ledger uses the same 100-clean-trade floor.
MIN_CLEAN_TRADES = 100
MIN_WALK_FORWARD_TRADES = 30
MIN_TIMEFRAME_TRADES = 20
TARGET_SCORE = 90


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _criterion(
    key: str,
    passed: bool,
    value: Any,
    target: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": key,
        "passed": bool(passed),
        "value": value,
        "target": target,
        "reason": reason,
    }


def evaluate(performance: Mapping[str, Any], raw_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a truthful 0-100 readiness score and its blockers.

    The result is intentionally observe-only.  It does not change thresholds,
    weights, RiskGate state, or paper execution.
    """
    raw_summary = raw_summary or {}
    total = int(_number(performance.get("total_trades")) or 0)
    verified = int(_number(performance.get("verified")) or 0)
    if not verified:
        # Synthetic callers may omit the additive field; the clean snapshot is
        # already built from learning-grade outcomes in that case.
        verified = total
    sample_ok = total >= MIN_CLEAN_TRADES and verified >= MIN_CLEAN_TRADES

    expectancy = _number(performance.get("expectancy_r"))
    expectancy_ok = expectancy is not None and expectancy > 0

    sharpe = _number(performance.get("sharpe"))
    sharpe_ok = sharpe is not None and sharpe > 0

    walk = dict(raw_summary.get("walk_forward") or {})
    wf_test = int(_number(walk.get("test_window")) or 0)
    wf_sharpe = _number(walk.get("test_sharpe"))
    wf_win_rate = _number(walk.get("test_win_rate"))
    walk_ok = (
        wf_test >= MIN_WALK_FORWARD_TRADES
        and wf_sharpe is not None
        and wf_sharpe > 0
        and wf_win_rate is not None
        and wf_win_rate >= 0.55
    )

    by_tf = dict(performance.get("by_timeframe") or {})
    eligible_tf = {
        str(tf): row
        for tf, row in by_tf.items()
        if isinstance(row, Mapping)
        and int(_number(row.get("trades")) or 0) >= MIN_TIMEFRAME_TRADES
    }
    unstable_tf = sorted(
        tf
        for tf, row in eligible_tf.items()
        if (_number(row.get("avg_r")) is None or _number(row.get("avg_r")) < 0)
    )
    timeframe_ok = bool(eligible_tf) and not unstable_tf

    close = dict(raw_summary.get("by_close_reason") or {})
    sl = dict(close.get("SL_HIT") or {})
    sl_trades = int(_number(sl.get("trades")) or 0)
    sl_rate = sl_trades / total if total else 0.0
    sl_avg_r = _number(sl.get("avg_r"))
    exit_ok = sl_rate <= 0.25 and (sl_avg_r is None or sl_avg_r > -1.0)

    excluded = int(_number(performance.get("excluded_from_learning")) or 0)
    excluded_rate = excluded / max(1, int(_number(raw_summary.get("outcomes_total")) or total))
    provenance_ok = excluded_rate <= 0.10

    criteria = [
        _criterion(
            "clean_sample",
            sample_ok,
            {"clean_trades": total, "verified": verified},
            f">={MIN_CLEAN_TRADES} clean ve doğrulanmış işlem",
            "Yeterli temiz ve doğrulanmış örneklem yok." if not sample_ok else "Örneklem eşiği sağlandı.",
        ),
        _criterion(
            "positive_expectancy",
            expectancy_ok,
            expectancy,
            ">0 R",
            "Beklenen değer negatif veya hesaplanamıyor." if not expectancy_ok else "Beklenen değer pozitif.",
        ),
        _criterion(
            "positive_sharpe",
            sharpe_ok,
            sharpe,
            ">0 Sharpe",
            "Risk-ayarlı getiri negatif veya hesaplanamıyor." if not sharpe_ok else "Risk-ayarlı getiri pozitif.",
        ),
        _criterion(
            "walk_forward",
            walk_ok,
            {"test_window": wf_test, "test_win_rate": wf_win_rate, "test_sharpe": wf_sharpe},
            f">={MIN_WALK_FORWARD_TRADES} dış örneklem, win-rate >=55%, Sharpe >0",
            "Dış örneklem kanıtı henüz pozitif değil." if not walk_ok else "Dış örneklem kanıtı sağlandı.",
        ),
        _criterion(
            "timeframe_stability",
            timeframe_ok,
            {"eligible": sorted(eligible_tf), "negative": unstable_tf},
            "Yeterli örnekli zaman dilimlerinin tümünde avg R >=0",
            f"Negatif zaman dilimleri: {', '.join(unstable_tf)}." if unstable_tf else "Zaman dilimi istikrarı sağlandı.",
        ),
        _criterion(
            "exit_quality",
            exit_ok,
            {"sl_hit_rate": round(sl_rate, 4), "sl_avg_r": sl_avg_r},
            "SL_HIT <=25% ve ortalama SL R >-1",
            "Stop kayıpları hâlâ yüksek veya aşırı." if not exit_ok else "Stop/çıkış karnesi eşiği sağlandı.",
        ),
        _criterion(
            "provenance_quality",
            provenance_ok,
            {"excluded": excluded, "excluded_rate": round(excluded_rate, 4)},
            "Öğrenme dışı kayıt oranı <=10%",
            "Kayıt kökeni eksik olan işlemler oranı yüksek." if not provenance_ok else "Kayıt kökeni yeterli.",
        ),
    ]
    passed = sum(1 for item in criteria if item["passed"])
    score = round(100 * passed / len(criteria), 1)
    blockers = [item["id"] for item in criteria if not item["passed"]]
    return {
        "score": score,
        "target_score": TARGET_SCORE,
        "status": "READY_FOR_OWNER_REVIEW" if score >= TARGET_SCORE else "WAITING_EVIDENCE",
        "criteria_passed": passed,
        "criteria_total": len(criteria),
        "blockers": blockers,
        "criteria": criteria,
        "shadow_only": True,
        "paper_safe": True,
        "no_execution": True,
        "automatic_activation": False,
        "policy": "Bu puan raporlama kapısıdır; eşik, ağırlık, RiskGate veya emir akışını değiştirmez.",
    }


__all__ = ["evaluate"]
