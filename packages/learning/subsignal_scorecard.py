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

v2 — CETVEL SERTLEŞTİRME (ölçüm bilimi düzeltmeleri; sinyaller değişmedi):
1. BİNDİRMESİZ örnekleme: adım = ufuk (H). v1 her barda örnek alıyordu →
   ardışık ileri-getiriler %85+ aynı hareketi paylaşıyor, n şişkin çıkıyordu.
2. TF-ADİL kıyas: `edge_ratio` = edge / o TF'in tipik |hareket|'i. Mutlak
   eşik (±0.15 puan) 1d'de kolay, 15m'de imkânsızdı (ölçek yanılsaması).
3. TABAN ÇİZGİSİ: `baseline_edge_pct` = "hep yukarı de" getirisi. Boğa
   döneminde her trend sinyali bedava pozitif görünür; EDGE damgası artık
   tabanı GEÇMEYİ şart koşar (rejim karışması ayrışır).
4. KARARLILIK: pencere kronolojik ikiye bölünür; iki yarıda aynı işaretli
   edge vermeyen sinyal EDGE damgası alamaz (tek-döneme ezber elenir).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from packages.data.providers.ohlcv import get_bars, history
from packages.data.providers.rotation.engine import ROTATION_SYMBOLS
from packages.data.providers.technical import indicators
from packages.data.providers.technical.timeframe import (
    _EMA_PERIODS,
    _MACD_ATR_FULL,
    _clamp,
    _ema_stack,
)
from packages.signals import (
    bollinger_fade,
    candle_rejection,
    market_structure,
    rsi_extreme,
    vwap_fade,
)

FLAG = "SUBSIGNAL_SCORECARD_ENABLED"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})
# D5 — worker koşum aralığı (sn): karne haftalık yeniden ölçülür (koşu ~26sn,
# her cycle koşmak bütçeyi yer; arşiv de günde bir bardan hızlı büyümez).
_INTERVAL_ENV = "SUBSIGNAL_SCORECARD_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 7 * 24 * 3600
# Cetvel sürümü: artifact bu sürümle üretilmediyse "taze" sayılmaz — cetvel
# değişince (v1→v2 gibi) eski ölçüm interval'i beklemeden yeniden üretilir.
_ENGINE = "subsignal_scorecard_v2"
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


# EDGE için sinyal, TF'in tipik hareketinin en az %10'unu yakalamalı (TF-adil).
_EDGE_RATIO_MIN = 0.10


def _verdict(
    edge_ratio: float, n: int, *, beats_baseline: bool, stable: bool
) -> str:
    """v2 damga: oran (TF-adil) + taban çizgisini geçme + iki-yarı kararlılık.
    INVERSE yalnız orana bakar (uyarıdır, terfi değil — sertleştirilmez)."""
    if n < 20:
        return "INSUFFICIENT"
    if edge_ratio >= _EDGE_RATIO_MIN and beats_baseline and stable:
        return "EDGE"
    if edge_ratio <= -_EDGE_RATIO_MIN:
        return "INVERSE"
    return "FLAT"


def _mean(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


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
        # v2: kronolojik iki-yarı edge'leri (kararlılık) — sig -> [yarıA, yarıB]
        halves: dict[str, tuple[list[float], list[float]]] = {}
        all_fwd: list[float] = []          # taban çizgisi + tipik hareket için
        n_points = 0
        used_syms = 0
        for sym in syms:
            # Arşiv + canlı birleşik pencere (BAR_HISTORY_ENABLED OFF iken arşiv
            # boş döner → yalnız canlı barlar, v2 ile bayt-aynı). Arşiv büyüdükçe
            # ölçüm penceresi _MAX_BARS tavanını aşar — kanıt haftayla büyür.
            bars = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
            if len(bars) < _MIN_WARMUP + H + 1:
                continue
            used_syms += 1
            closes_all = [b.close for b in bars]
            mid = (_MIN_WARMUP + len(bars) - H) // 2  # sembolün kronolojik ortası
            # v2: adım = H → bindirmesiz örnekler (gerçek bağımsız n)
            for i in range(_MIN_WARMUP, len(bars) - H, H):
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
                # Bollinger band-fade: banda değme mean-reversion (her TF ölçülür)
                bf = bollinger_fade.lean(closes_all[: i + 1])
                if bf is not None:
                    leans["bollinger_fade"] = bf
                # Candle-rejection: rejeksiyon mumu = giriş zamanlaması (kapalı dedektör reuse)
                cr = candle_rejection.lean(bars[: i + 1])
                if cr is not None:
                    leans["candle_rejection"] = cr
                if not leans:
                    continue
                n_points += 1
                fwd = (closes_all[i + H] - base) / base * 100.0  # yüzde ileri getiri
                all_fwd.append(fwd)
                for sig, lean in leans.items():
                    if lean == 0:
                        continue
                    aligned = fwd if lean > 0 else -fwd
                    acc.setdefault(sig, []).append(aligned)
                    hits.setdefault(sig, []).append(1 if aligned > 0 else 0)
                    ha, hb = halves.setdefault(sig, ([], []))
                    (ha if i < mid else hb).append(aligned)
        # v2 TF-seviyesi referanslar: tipik |hareket| (adil kıyas paydası) ve
        # "hep yukarı de" taban getirisi (rejim karışması kontrolü).
        typical_move = _mean([abs(f) for f in all_fwd])
        baseline_edge = _mean(all_fwd)
        signals = {}
        for sig, arr in acc.items():
            n = len(arr)
            edge = _mean(arr)
            hr = sum(hits[sig]) / n if n else 0.0
            ratio = edge / typical_move if typical_move > 0 else 0.0
            ha, hb = halves.get(sig, ([], []))
            edge_a, edge_b = _mean(ha), _mean(hb)
            # Kararlılık: iki yarıda da örnek var ve edge aynı işaretli.
            stable = bool(ha and hb and edge_a * edge_b > 0)
            signals[sig] = {
                "n": n,
                "edge_pct": round(edge, 4),
                "hit_rate": round(hr, 4),
                "edge_ratio": round(ratio, 4),
                "edge_first_half": round(edge_a, 4),
                "edge_second_half": round(edge_b, 4),
                "stable": stable,
                "beats_baseline": bool(edge > abs(baseline_edge)),
                "verdict": _verdict(
                    ratio, n,
                    beats_baseline=edge > abs(baseline_edge),
                    stable=stable,
                ),
            }
        per_tf[tf] = {
            "horizon_bars": H,
            "symbols_used": used_syms,
            "points": n_points,
            "typical_move_pct": round(typical_move, 4),
            "baseline_edge_pct": round(baseline_edge, 4),
            "signals": signals,
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": _ENGINE,
        "universe_n": len(syms),
        "per_timeframe": per_tf,
        "note": (
            "İZOLE salt-gözlem (v2 sert cetvel): bindirmesiz örnekleme + "
            "TF-adil edge_ratio + taban-çizgisi kontrolü + iki-yarı kararlılık. "
            "EDGE damgası = oran≥0.10 VE tabanı geçer VE iki yarıda tutarlı. "
            "Canlı skora/karara dokunmaz."
        ),
    }


def artifact_path() -> Path:
    """İzole karne artifact'ının yolu (API bunu sunar; exit_forensics deseni)."""
    return Path(_ART)


def _write(payload: dict) -> None:
    path = artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


def run_if_due() -> dict:
    """D5 worker-adımı: flag AÇIK + artifact bayatsa yeniden ölç; tazeyken SKIP.
    Durum = artifact'ın kendisi (generated_at) — ayrı tetik dosyası yok.
    Bozuk/eksik artifact → dürüstçe yeniden üretilir. KAPALIYKEN tam no-op."""
    if not enabled():
        return {"status": "DISABLED"}
    try:
        path = artifact_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            # Eski-cetvel artifact'ı (engine farklı) taze sayılmaz: v1 kaydı
            # v2 ölçümünü bir hafta bloke etmesin (canlıda yakalanan hata).
            if data.get("engine") == _ENGINE and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass  # okunamayan durum → yeniden ölçüm en dürüst yol
    rep = analyze()
    _write(rep)
    return {"status": "OK", "timeframes": list(rep["per_timeframe"])}


__all__ = ["FLAG", "analyze", "artifact_path", "enabled", "run_if_due", "sub_leans"]
