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


def _agg_metrics(symbols: list[str], timeframe: str) -> dict:
    """Aktif override altında sembol-seti üstünde backtest'i TRADE-AĞIRLIKLI birleştir.
    Global eşikler (bias_cuts/adx) tek sembolde değil, sepet üstünde doğrulanmalı."""
    total_trades = 0
    total_wins = 0.0
    weighted_ret = 0.0
    per_symbol: dict[str, dict] = {}
    for sym in symbols:
        r = strategy_backtest.run_signal_backtest(sym, timeframe)
        per_symbol[sym] = _metrics(r)
        n = int(r.get("total_trades") or 0)
        if n <= 0:
            continue
        total_trades += n
        total_wins += float(r.get("win_rate") or 0.0) * n
        weighted_ret += float(r.get("avg_return_pct") or 0.0) * n
    if total_trades <= 0:
        return {"status": "ok", "total_trades": 0, "win_rate": None,
                "avg_return_pct": None, "profit_factor": None, "per_symbol": per_symbol}
    return {
        "status": "ok",
        "total_trades": total_trades,
        "win_rate": round(total_wins / total_trades, 4),
        "avg_return_pct": round(weighted_ret / total_trades, 5),
        "profit_factor": None,
        "per_symbol": per_symbol,
    }


def sweep(
    param_path: str,
    values: list[float],
    *,
    symbol: str = "BTCUSD",
    timeframe: str = "1d",
    symbols: list[str] | None = None,
) -> dict:
    """`param_path` eşiğini `values` üzerinde tara; her değer için backtest metriği.

    En iyi = en yüksek avg_return_pct (yeterli trade'i olan; trade yoksa elenir).
    Baseline = aktif config değeri (override'sız koşu)."""
    baseline_value = _current_value(param_path)
    syms = symbols or [symbol]
    multi = len(syms) > 1

    def _measure() -> dict:
        if multi:
            return _agg_metrics(syms, timeframe)
        return _metrics(strategy_backtest.run_signal_backtest(syms[0], timeframe))

    runs: list[dict] = []
    for v in values:
        with threshold_override(_nested(param_path, v)):
            result = _measure()
        runs.append({"value": v, **result})

    # Baseline (override yok) — referans.
    base_result = _measure()

    ranked = [
        r for r in runs
        if r.get("avg_return_pct") is not None and (r.get("total_trades") or 0) > 0
    ]
    best = max(ranked, key=lambda r: r["avg_return_pct"]) if ranked else None

    return {
        "param_path": param_path,
        "symbol": symbol if not multi else None,
        "symbols": syms,
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
