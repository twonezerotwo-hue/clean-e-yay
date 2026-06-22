"""Geçici (ephemeral) asset teknik analizi — gözlemci, kalıcı değil.

Herhangi bir DESTEKLENEN sembol için mevcut teknik pipeline'ı (get_bars +
compute_snapshot) on-demand çalıştırır: multi-TF RSI/MACD/EMA/skor + momentum.
İşlem evrenine EKLEMEZ, otomatik işlem AÇMAZ (NO_EXECUTION). Veri yoksa
`available=False` döner (uydurma/mock YOK — DATA_POLICY).
"""
from __future__ import annotations

from packages.data.providers.ohlcv import get_bars
from packages.data.providers.technical import compute_snapshot

TIMEFRAMES = ["1d", "4h", "1h"]


def _direction(score: float) -> str:
    if score >= 55.0:
        return "bullish"
    if score <= 45.0:
        return "bearish"
    return "neutral"


def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-1 - n] == 0:
        return None
    return round((closes[-1] - closes[-1 - n]) / closes[-1 - n] * 100.0, 2)


def analyze_symbol(symbol: str) -> dict:
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"symbol": sym, "available": False, "reason": "sembol bos"}

    tfs: dict[str, dict] = {}
    closes_1d: list[float] | None = None
    last_price: float | None = None

    for tf in TIMEFRAMES:
        bars = get_bars(sym, tf)
        if not bars:
            continue
        snap = compute_snapshot(sym, tf, bars)
        tfs[tf] = {
            "score": round(float(snap.score), 1),
            "direction": _direction(float(snap.score)),
            "rsi": round(float(snap.rsi), 1) if snap.rsi is not None else None,
            "ema_stack": snap.ema_stack,
            "atr": round(float(snap.atr), 4) if snap.atr is not None else None,
            "bars_used": snap.bars_used,
            "status": snap.status,
        }
        if tf == "1d":
            closes_1d = [float(b.close) for b in bars if b.close is not None]
            if bars and bars[-1].close is not None:
                last_price = float(bars[-1].close)

    if not tfs:
        return {
            "symbol": sym,
            "available": False,
            "reason": "veri kaynagi yok — desteklenen sembol degil (provider/ticker tanimsiz)",
        }

    momentum: dict[str, float | None] = {}
    if closes_1d:
        for label, n in (("1D", 1), ("7D", 7), ("30D", 30)):
            momentum[label] = _ret(closes_1d, n)

    scores = [v["score"] for v in tfs.values()]
    overall = round(sum(scores) / len(scores), 1)

    return {
        "symbol": sym,
        "available": True,
        "last_price": last_price,
        "overall_score": overall,
        "overall_direction": _direction(overall),
        "timeframes": tfs,
        "momentum_pct": momentum,
        "note": "Gozlemci teknik analiz — islem evreni disi, otomatik islem yok (NO_EXECUTION).",
    }
