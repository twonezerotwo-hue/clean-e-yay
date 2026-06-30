"""CP2 — Edge kanıt/stabilite katmanı (hafif, deterministik, observe-only).

Gerçek backtest motoru ZATEN VAR (packages/data/strategy_backtest.py canlı
teknik motoru geçmiş barlarda yeniden çalıştırır; packages/data/backtest.py R2
rolling). Bu modül onu TEKRARLAMAZ — eksik olan **karar-değeri taşıyan kanıt
sentezini** ekler: biriken kapalı outcome'lar üstünde **çok-katlı walk-forward
stabilite** (edge zaman içinde tutarlı mı, fluke mı?) + missed_opportunity
counterfactual (açmadıklarımızın sonucu). CP4 öz-ayar bir öneriyi uygulamadan
ÖNCE buraya bakıp "edge yeterince stabil mi" diye güven tartar.

Hafif: yalnız mevcut outcomes (~yüzlerce kayıt) üstünde aritmetik — ağır
historical-bar backtest'i BUNDLE ETMEZ (o ayrı endpoint'te, on-demand). Off-tick.
PAPER_SAFE / observe-only — karar zincirini etkilemez.
"""
from __future__ import annotations

# Stabilite eşikleri (açık, sabit; magic-number değil). win_rate fold'lar arası
# std bu sınırın altında VE fold'ların çoğu pozitif expectancy ise edge "stabil".
_MAX_WIN_RATE_STD = 0.15
_MIN_FOLDS = 4
_MIN_PER_FOLD = 3


def walk_forward_stability(pnls: list[float], folds: int = _MIN_FOLDS) -> dict:
    """Sıralı pnl serisini `folds` ardışık segmente böl; segmentler arası
    win_rate tutarlılığını ölç. summary'deki tek 70/30'u çok-katlı stabiliteye
    genişletir (edge gerçek mi, fluke mı sinyali)."""
    n = len(pnls)
    if n < folds * _MIN_PER_FOLD:
        return {"ready": False, "reason": "insufficient_outcomes", "have": n,
                "need": folds * _MIN_PER_FOLD, "segments": []}
    size = n // folds
    segments: list[dict] = []
    for f in range(folds):
        seg = pnls[f * size:] if f == folds - 1 else pnls[f * size:(f + 1) * size]
        wins = sum(1 for p in seg if p > 0)
        segments.append({
            "n": len(seg),
            "win_rate": round(wins / len(seg), 3) if seg else 0.0,
            "expectancy": round(sum(seg) / len(seg), 2) if seg else 0.0,
        })
    wrs = [s["win_rate"] for s in segments]
    mean = sum(wrs) / len(wrs)
    std = (sum((w - mean) ** 2 for w in wrs) / len(wrs)) ** 0.5
    positive_folds = sum(1 for s in segments if s["expectancy"] > 0)
    stable = std <= _MAX_WIN_RATE_STD and positive_folds >= folds - 1
    return {
        "ready": True,
        "folds": folds,
        "segments": segments,
        "win_rate_std": round(std, 3),
        "positive_folds": positive_folds,
        "stable": stable,
    }


def report() -> dict:
    """Edge kanıt özeti: stabilite + counterfactual + tek-kelime verdict."""
    from packages.learning import missed_opportunity
    from packages.learning import outcomes as outcomes_mod

    outs = outcomes_mod.outcomes_from_state()
    pnls = [o.pnl for o in outs]
    stab = walk_forward_stability(pnls)

    mo = missed_opportunity.summary_viewmodel()
    moc = mo.get("outcomes") or {}
    counterfactual = {
        "missed_win": int(moc.get("missed_win", 0) or 0),
        "avoided_loss": int(moc.get("avoided_loss", 0) or 0),
        "expired": int(moc.get("expired", 0) or 0),
    }

    if not stab["ready"]:
        verdict = "INSUFFICIENT"
    elif stab["stable"]:
        verdict = "STABLE"
    else:
        verdict = "UNSTABLE"

    return {
        "total": len(outs),
        "verdict": verdict,
        "stability": stab,
        "counterfactual": counterfactual,
        # CP4 bu raporu öneri-doğrulamada okuyacak; UNSTABLE iken oto-uygulama
        # yapılmamalı (güven yok) — politika CP4'te bağlanır.
        "safe_to_autotune": verdict == "STABLE",
    }
