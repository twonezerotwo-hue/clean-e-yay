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
    results = [(sym, strategy_backtest.run_signal_backtest(sym, timeframe))
               for sym in symbols]
    return _agg_from_results(results)


def _agg_from_results(results: list[tuple[str, dict]]) -> dict:
    """Ham (sembol, sonuç) çiftlerinden trade-ağırlıklı birleşim (Y-4: walk-forward
    modu backtest'i yeniden KOŞMADAN aynı birleşimi kullanır — çıktı birebir)."""
    total_trades = 0
    total_wins = 0.0
    weighted_ret = 0.0
    per_symbol: dict[str, dict] = {}
    for sym, r in results:
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


# ── Y-4: walk-forward doğrulama (freqtrade deseni) ──────────────────────────────
# Aday eşik EĞİTİM penceresinde (ilk split_ratio) seçilir, DOĞRULAMA penceresinde
# (kalan) baseline'ı geçmeden öneri OLMAZ — tek pencerede parlayan aşırı-uyum
# adayı kapıda ölür. Flag `threshold_ab.walk_forward` DEFAULT OFF = mevcut çıktı
# birebir (yeni anahtar bile eklenmez). Motora dokunulmaz: bölme, backtest'in
# ZATEN döndürdüğü trade listesinin entry_ts'i üzerinden yapılır.

_SPLIT_RATIO_DEFAULT = 0.7


def _wf_cfg() -> dict:
    try:
        return load_thresholds().get("threshold_ab") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def walk_forward_enabled() -> bool:
    """`threshold_ab.walk_forward` owner-flag (DEFAULT OFF = tek-pencere davranışı)."""
    return bool(_wf_cfg().get("walk_forward", False))


def _trade_seg_metrics(trades: list[dict]) -> dict:
    """Trade alt-kümesi → sweep metrik şekli (motorla aynı formüller)."""
    n = len(trades)
    if not n:
        return {"total_trades": 0, "win_rate": None,
                "avg_return_pct": None, "profit_factor": None}
    wins = [t for t in trades if float(t.get("pnl_pct") or 0.0) > 0]
    losses = [t for t in trades if float(t.get("pnl_pct") or 0.0) <= 0]
    gross_p = sum(float(t["pnl_pct"]) for t in wins)
    gross_l = abs(sum(float(t["pnl_pct"]) for t in losses))
    return {
        "total_trades": n,
        "win_rate": round(len(wins) / n, 4),
        "avg_return_pct": round(sum(float(t["pnl_pct"]) for t in trades) / n, 5),
        "profit_factor": round(gross_p / gross_l, 3) if gross_l > 0 else None,
    }


def _wf_split(results: list[dict], split_ratio: float) -> tuple[dict, dict]:
    """Ham backtest sonuç(lar)ı → (eğitim, doğrulama) metrikleri.

    Bölme her sembolün KENDİ zaman penceresinde yapılır (from + ratio×(to−from));
    segment trade'leri sembollerarası birleştirilir (trade-ağırlıklı doğal olarak)."""
    from datetime import datetime

    train: list[dict] = []
    val: list[dict] = []
    for r in results:
        trades = r.get("trades") or []
        w = r.get("window") or {}
        try:
            t0 = datetime.fromisoformat(str(w.get("from")))
            t1 = datetime.fromisoformat(str(w.get("to")))
        except (ValueError, TypeError):
            continue  # penceresiz sonuç (INSUFFICIENT) bölünemez
        split_ts = t0 + (t1 - t0) * split_ratio
        for t in trades:
            try:
                ts = datetime.fromisoformat(str(t.get("entry_ts")))
            except (ValueError, TypeError):
                continue
            (train if ts <= split_ts else val).append(t)
    return _trade_seg_metrics(train), _trade_seg_metrics(val)


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
    Baseline = aktif config değeri (override'sız koşu).

    Y-4 walk-forward (flag `threshold_ab.walk_forward`, DEFAULT OFF = bu çıktı
    birebir): AÇIKKEN aday EĞİTİM penceresinde seçilir ve DOĞRULAMA penceresinde
    baseline'ı geçmeden `recommendation` üretilmez (aşırı-uyum kapıda ölür).
    Tüketici (threshold_trainer) yalnız `recommendation` okuduğundan flag
    yalnızca SIKILAŞTIRIR."""
    baseline_value = _current_value(param_path)
    syms = symbols or [symbol]
    multi = len(syms) > 1
    wf = walk_forward_enabled()
    try:
        split_ratio = float(_wf_cfg().get("split_ratio", _SPLIT_RATIO_DEFAULT))
    except (ValueError, TypeError):
        split_ratio = _SPLIT_RATIO_DEFAULT
    split_ratio = max(0.5, min(0.9, split_ratio))  # dejenere bölme yok

    def _measure() -> dict:
        if multi:
            return _agg_metrics(syms, timeframe)
        return _metrics(strategy_backtest.run_signal_backtest(syms[0], timeframe))

    def _measure_wf() -> dict:
        raws = [(s, strategy_backtest.run_signal_backtest(s, timeframe)) for s in syms]
        full = _agg_from_results(raws) if multi else _metrics(raws[0][1])
        tr, va = _wf_split([r for _, r in raws], split_ratio)
        return {**full, "train": tr, "validation": va}

    measure = _measure_wf if wf else _measure

    runs: list[dict] = []
    for v in values:
        with threshold_override(_nested(param_path, v)):
            result = measure()
        runs.append({"value": v, **result})

    # Baseline (override yok) — referans.
    base_result = measure()

    if wf:
        # Seçim eğitim penceresinde; trade'siz/verisiz aday elenir.
        ranked = [
            r for r in runs
            if (r.get("train") or {}).get("avg_return_pct") is not None
        ]
        best = (
            max(ranked, key=lambda r: r["train"]["avg_return_pct"]) if ranked else None
        )
        base_tr = (base_result.get("train") or {}).get("avg_return_pct")
        base_va = (base_result.get("validation") or {}).get("avg_return_pct")
        best_va = ((best or {}).get("validation") or {}).get("avg_return_pct")
        recommendation = (
            best
            if best is not None
            and base_tr is not None and base_va is not None and best_va is not None
            and best["train"]["avg_return_pct"] > base_tr
            and best_va > base_va          # doğrulama penceresi TEYİDİ şart
            else None
        )
    else:
        ranked = [
            r for r in runs
            if r.get("avg_return_pct") is not None and (r.get("total_trades") or 0) > 0
        ]
        best = max(ranked, key=lambda r: r["avg_return_pct"]) if ranked else None
        recommendation = (
            best
            if best
            and base_result.get("avg_return_pct") is not None
            and best["avg_return_pct"] > base_result["avg_return_pct"]
            else None
        )

    out = {
        "param_path": param_path,
        "symbol": symbol if not multi else None,
        "symbols": syms,
        "timeframe": timeframe,
        "baseline_value": baseline_value,
        "baseline": (
            {**_metrics(base_result), "train": base_result.get("train"),
             "validation": base_result.get("validation")}
            if wf else _metrics(base_result)
        ),
        "runs": runs,
        "best": best,
        # Öneri yalnızca açıkça daha iyiyse (wf modunda: iki pencerede de).
        "recommendation": recommendation,
    }
    if wf:
        out["walk_forward"] = {"enabled": True, "split_ratio": split_ratio}
    return out


__all__ = ["sweep"]
