"""Faz A — touche ALT-SİNYAL karnesi (İZOLE, salt-gözlem).

touche tek bir yön skoru üretir; bu modül onu momentum alt-sinyallerine
(trend / rsi / macd) AYIRIP her (timeframe) için hangi alt-sinyalin ileri
getiriyi (forward return) ayrıştırdığını ölçer. Amaç: "touche 1d'de iyi,
15m'de gürültü" bilmecesini alt-sinyal seviyesinde açmak → TF-başına ağırlık
öğrenmenin (Faz C) kanıt tabanı.

KURAL 1 — canlı skora/karara SIFIR dokunuş:
- Hiçbir canlı KARAR fonksiyonu çağrılmaz. Yalnız `timeframe.py`'den saf
  sabit/yardımcı (_MOM_WEIGHTS/_clamp/_ema_stack/_momentum_score) import edilir
  (kopya değil → formül drift'i yok) ve `indicators.py` ile ham gösterge
  yeniden hesaplanır.
- LOOK-AHEAD YOK: her indekste yalnız `bars[: i + 1]` görülür.
- İZOLE artifact yazar (`subsignal_scorecard.json`); canlı deftere/ağırlığa/
  paper'a ASLA dokunmaz.
- Flag `SUBSIGNAL_SCORECARD_ENABLED` (env, DEFAULT OFF) yalnız worker-adımı
  içindir; `analyze()` her zaman elle çağrılabilir (salt-ölçüm).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.providers.ohlcv import get_bars
from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
from packages.data.providers.technical import indicators
from packages.data.providers.technical.timeframe import (
    _EMA_PERIODS,
    _MACD_ATR_FULL,
    _clamp,
    _ema_stack,
)
from packages.signals import market_structure, rsi_extreme, vwap_fade

FLAG = "SUBSIGNAL_SCORECARD_ENABLED"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})
_TIMEFRAMES = ("15m", "1h", "4h", "1d")
# TF başına ileri-getiri ufku (kaç bar): kısa TF daha çok bar, uzun TF az.
_HORIZON = {"15m": 8, "1h": 8, "4h": 6, "1d": 5}
_MIN_WARMUP = 210  # ema200 (+rsi/macd) için yeterli geçmiş
_ART = "data/runtime/subsignal_scorecard.json"


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def sub_leans(closes: list[float], bars: list) -> dict[str, float]:
    """touche momentum alt-sinyal lean'leri (−1..+1). `_momentum_score` ile
    AYNI formül + AYNI sabitler (import; kopya değil). Anahtar yoksa o gösterge
    yetersiz. Salt-hesap; hiçbir yan etki yok."""
    rsi_v = indicators.rsi(closes)
    macd_t = indicators.macd(closes)
    atr_v = indicators.atr(bars)
    macd_atr = macd_t[2] / atr_v if (macd_t is not None and atr_v and atr_v > 0) else None
    emas = [indicators.ema(closes, p) for p in _EMA_PERIODS]
    ema_stack = _ema_stack(emas)
    out: dict[str, float] = {}
    if ema_stack is not None:
        out["trend"] = {"bullish": 1.0, "bearish": -1.0, "mixed": 0.0}[ema_stack]
    if rsi_v is not None:
        out["rsi"] = _clamp((rsi_v - 50.0) / 50.0, -1.0, 1.0)
    if macd_atr is not None:
        out["macd"] = _clamp(macd_atr / _MACD_ATR_FULL, -1.0, 1.0)
    return out


def _verdict(edge_pct: float, n: int) -> str:
    if n < 20:
        return "INSUFFICIENT"
    if edge_pct >= 0.15:
        return "EDGE"
    if edge_pct <= -0.15:
        return "INVERSE"
    return "FLAT"


def analyze(symbols: list[str] | None = None, timeframes=_TIMEFRAMES) -> dict:
    """Her (TF × alt-sinyal) için ileri-getiri ayrışımını ölç.

    Metrik `edge_pct` = ortalama(ileri_getiri × işaret(lean)) × 100 — sinyali
    takip etsen ortalama yön-getirisi. `hit_rate` = işaret(lean)==işaret(getiri)
    oranı. Pozitif edge = sinyal o TF'de yön öngörüyor; negatif = ters.
    """
    syms = symbols or sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD"})
    per_tf: dict[str, dict] = {}
    for tf in timeframes:
        H = _HORIZON.get(tf, 6)
        acc: dict[str, list[float]] = {}   # sig -> aligned forward returns (%)
        hits: dict[str, list[int]] = {}
        n_points = 0
        used_syms = 0
        for sym in syms:
            bars = get_bars(sym, tf) or []
            if len(bars) < _MIN_WARMUP + H + 1:
                continue
            used_syms += 1
            closes_all = [b.close for b in bars]
            for i in range(_MIN_WARMUP, len(bars) - H):
                base = closes_all[i]
                if not base:
                    continue
                leans = dict(sub_leans(closes_all[: i + 1], bars[: i + 1]))
                # Market structure (HH/HL + BOS/CHoCH) — momentum'un yanında peer
                # sinyal olarak ölçülür (aynı edge metriği). Fiyat-doğrudan → her TF.
                ms_lean = market_structure.lean(bars[: i + 1])
                if ms_lean is not None:
                    leans["structure"] = ms_lean
                # RSI-uç (fade): touche'un lineer RSI'ının TERSİ polaritede uç okuması
                rx = rsi_extreme.lean(closes_all[: i + 1])
                if rx is not None:
                    leans["rsi_extreme"] = rx
                # VWAP-fade (zengin vwap/engine reuse): intraday aşırı-sapma dönüşü
                vf = vwap_fade.lean(bars[: i + 1], timeframe=tf)
                if vf is not None:
                    leans["vwap_fade"] = vf
                if not leans:
                    continue
                n_points += 1
                fwd = (closes_all[i + H] - base) / base * 100.0  # yüzde ileri getiri
                for sig, lean in leans.items():
                    if lean == 0:
                        continue
                    aligned = fwd if lean > 0 else -fwd
                    acc.setdefault(sig, []).append(aligned)
                    hits.setdefault(sig, []).append(1 if aligned > 0 else 0)
        signals = {}
        for sig, arr in acc.items():
            n = len(arr)
            edge = sum(arr) / n if n else 0.0
            hr = sum(hits[sig]) / n if n else 0.0
            signals[sig] = {
                "n": n,
                "edge_pct": round(edge, 4),
                "hit_rate": round(hr, 4),
                "verdict": _verdict(edge, n),
            }
        per_tf[tf] = {
            "horizon_bars": H,
            "symbols_used": used_syms,
            "points": n_points,
            "signals": signals,
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": "subsignal_scorecard_v1",
        "universe_n": len(syms),
        "per_timeframe": per_tf,
        "note": (
            "İZOLE salt-gözlem: momentum alt-sinyalleri (trend/rsi/macd) + "
            "market_structure (HH/HL+BOS/CHoCH) TF başına ileri-getiri ayrışımı. "
            "edge_pct>0=öngörü, <0=ters. Canlı skora/karara dokunmaz."
        ),
    }


def _write(payload: dict) -> None:
    path = Path(_ART)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run() -> dict:
    """Worker-adımı: flag AÇIKSA analiz + artifact yaz; KAPALIYSA no-op."""
    if not enabled():
        return {"status": "DISABLED"}
    rep = analyze()
    _write(rep)
    return {"status": "OK", "timeframes": list(rep["per_timeframe"])}


__all__ = ["FLAG", "analyze", "enabled", "run", "sub_leans"]
