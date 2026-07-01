"""CP4 — eşik A/B parametre-taraması (config-injection seam tüketicisi).

`load_thresholds` üstündeki `threshold_override` seam'i sayesinde bir eşik
parametresinin (ör. `paper_trading.sl_pct`, `consensus.min_confidence`) farklı
değerlerini MEVCUT backtest motoruyla (strategy_backtest.run_signal_backtest)
geçmiş barlarda dener ve karşılaştırır. Yeni motor YOK — seam + mevcut backtest.

Amaç: bir eşik nudge'ı CANLIYA uygulanmadan ÖNCE "tarihsel olarak daha iyi mi"
sorusunu güvenle yanıtlamak (CP4'ün 'trainer öner → backtest doğrula' adımı).
Observe-only / on-demand — karar zincirine canlı etkisi yoktur; yalnız override'ı
backtest scope'unda enjekte eder, scope dışında base bayt-aynı.
"""
from __future__ import annotations

from packages.data import strategy_backtest
from packages.data.registry.loader import load_thresholds, threshold_override


def _nested(path: str, value) -> dict:
    """'a.b.c', v → {'a': {'b': {'c': v}}} (deep-merge override için)."""
    keys = path.split(".")
    out: dict = {}
    cur = out
    for k in keys[:-1]:
        cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value
    return out


def _current_value(path: str):
    """Aktif (base) eşik değeri — taramanın 'baseline'ı."""
    node = load_thresholds()
    for k in path.split("."):
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


def _metrics(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "total_trades": result.get("total_trades"),
        "win_rate": result.get("win_rate"),
        "avg_return_pct": result.get("avg_return_pct"),
        "profit_factor": result.get("profit_factor"),
    }


def sweep(
    param_path: str,
    values: list[float],
    *,
    symbol: str = "BTCUSD",
    timeframe: str = "1d",
) -> dict:
    """`param_path` eşiğini `values` üzerinde tara; her değer için backtest metriği.

    En iyi = en yüksek avg_return_pct (yeterli trade'i olan; trade yoksa elenir).
    Baseline = aktif config değeri (override'sız koşu)."""
    baseline_value = _current_value(param_path)

    runs: list[dict] = []
    for v in values:
        with threshold_override(_nested(param_path, v)):
            result = strategy_backtest.run_signal_backtest(symbol, timeframe)
        runs.append({"value": v, **_metrics(result)})

    # Baseline (override yok) — referans.
    base_result = strategy_backtest.run_signal_backtest(symbol, timeframe)

    ranked = [
        r for r in runs
        if r.get("avg_return_pct") is not None and (r.get("total_trades") or 0) > 0
    ]
    best = max(ranked, key=lambda r: r["avg_return_pct"]) if ranked else None

    return {
        "param_path": param_path,
        "symbol": symbol,
        "timeframe": timeframe,
        "baseline_value": baseline_value,
        "baseline": _metrics(base_result),
        "runs": runs,
        "best": best,
        # Öneri yalnızca açıkça daha iyiyse (best baseline'dan yüksek avg_return).
        "recommendation": (
            best
            if best
            and base_result.get("avg_return_pct") is not None
            and best["avg_return_pct"] > base_result["avg_return_pct"]
            else None
        ),
    }


__all__ = ["sweep"]
