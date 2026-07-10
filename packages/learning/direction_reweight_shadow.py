"""Yön yeniden-ağırlık GÖLGESİ — owner'ın yapı-ağırlıklı yön tezi (İZOLE, salt-gözlem).

Mevcut touche YÖN skoru momentum çorbasıdır: trend %40 + RSI %30 + MACD %30
(`_momentum_score`), RSI HER ZAMAN oy verir. Owner'ın tezi (2026-07-09, kalibre
edilip ileri-veride doğrulandı): **yapı öne, RSI rol-kısıtlı**. Bu modül owner'ın
yeniden-ağırlıklı yön skorunu touche'un yanında GÖLGE olarak her barda üretir ve
ikisini AYNI barlarda ileri-getiriyle yarıştırır — "owner ağırlığı touche'tan daha
iyi mi yön ayırıyor" sorusunu KANITLA cevaplar.

İki yön skoru (her ikisi de −1..+1):
  A) TOUCHE (çorba): (_momentum_score − 50)/50 — üretim formülünün AYNISI (import,
     kopya değil → drift yok).
  B) OWNER (yapı-ağırlıklı + rol-kısıtlı):
       struct = market_structure.lean  (HH/HL + BOS/CHoCH, fiyat-doğrudan)
       mom    = 0.5·EMA_stack + 0.5·MACD
       ADX ≥ 22 (trend modu):  owner = 0.64·struct + 0.36·mom          (RSI SUSAR)
       ADX < 22 (range modu):  owner = 0.50·struct + 0.28·mom + 0.22·RSI (RSI konuşur)
     Owner kuralı birebir: RSI trend-takip sisteminde YÖN üretmez; yalnız range/
     dönüş modunda söz hakkı alır. Yapı ana motordur.

KURALLAR (subsignal_scorecard deseniyle aynı disiplin):
- Canlı skora/karara/paper'a SIFIR dokunuş. İZOLE artifact yazar.
- LOOK-AHEAD YOK: her indekste yalnız `bars[: i + 1]`.
- BİNDİRMESİZ örnekleme (adım = ufuk H) → gerçek bağımsız n.
- ADİL PAIRED kıyas: iki skor AYNI bar kümesinde ölçülür (biri hesaplanamıyorsa o
  bar ikisi için de atlanır) → edge farkı skordan gelir, örneklemden değil.
- İki-yarı KARARLILIK: owner üstünlüğü tek döneme ezber değilse damgalanır.
- Flag `DIRECTION_REWEIGHT_SHADOW` (env, DEFAULT OFF) yalnız worker-adımı içindir;
  `analyze()` her zaman elle çağrılabilir (salt-ölçüm). Kapalıyken tam no-op.

Owner onayı OLMADAN touche ağırlıkları DEĞİŞMEZ (KIRMIZI ÇİZGİ). Bu yalnız kanıt
üretir: ileri-veride de tutarsa owner _MOM_WEIGHTS revizyonunu onaylar.
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
    _momentum_score,
)
from packages.signals import market_structure

FLAG = "DIRECTION_REWEIGHT_SHADOW"
_ENV_TRUE = frozenset({"1", "true", "yes", "on"})
_INTERVAL_ENV = "DIRECTION_REWEIGHT_SHADOW_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 7 * 24 * 3600
_ENGINE = "direction_reweight_shadow_v1"
_TIMEFRAMES = ("15m", "1h", "4h", "1d")
_HORIZON = {"15m": 8, "1h": 8, "4h": 6, "1d": 5}
_MIN_WARMUP = 210  # ema200 (+rsi/macd/adx) için yeterli geçmiş
_ART = "data/runtime/direction_reweight_shadow.json"

_ADX_TREND = 22.0     # ADX bu eşiğin üstünde → trend modu (RSI susar)
_DIR_EPS = 0.05       # |lean| bu eşiğin altındaysa "yön yok" (nötr, örnek dışı)
_FLAT_MAX = 0.2       # fitilsiz (high==low) bar oranı tavanı — o sembol×TF atlanır
# Owner üstünlüğü damgası: edge farkı tipik hareketin en az %8'i olmalı (TF-adil).
_EDGE_MARGIN_RATIO = 0.08


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in _ENV_TRUE


def leans(closes: list[float], bars: list) -> tuple[float, float] | None:
    """(touche_lean, owner_lean) ∈ [−1,1] veya None (ikisi de hesaplanamıyorsa).

    Salt-hesap; hiçbir yan etki yok. touche = üretim `_momentum_score`'unun
    −1..+1'e ölçeklenmişi. owner = yapı-ağırlıklı + ADX-kapılı RSI rol-kısıtı."""
    rsi_v = indicators.rsi(closes)
    macd_t = indicators.macd(closes)
    atr_v = indicators.atr(bars)
    macd_atr = macd_t[2] / atr_v if (macd_t is not None and atr_v and atr_v > 0) else None
    emas = [indicators.ema(closes, p) for p in _EMA_PERIODS]
    ema_stack = _ema_stack(emas)
    if rsi_v is None or macd_atr is None or ema_stack is None:
        return None
    struct = market_structure.lean(bars)
    if struct is None:
        return None

    # A) touche çorbası — üretim formülü (drift yok).
    mom_score = _momentum_score(rsi_v, macd_atr, ema_stack)
    if mom_score is None:
        return None
    touche = _clamp((mom_score - 50.0) / 50.0, -1.0, 1.0)

    # B) owner — yapı öne, RSI rol-kısıtlı (ADX rejim kapısı).
    stack_sign = {"bullish": 1.0, "bearish": -1.0, "mixed": 0.0}[ema_stack]
    rsi_lean = _clamp((rsi_v - 50.0) / 50.0, -1.0, 1.0)
    macd_lean = _clamp(macd_atr / _MACD_ATR_FULL, -1.0, 1.0)
    mom = 0.5 * stack_sign + 0.5 * macd_lean
    adx_t = indicators.adx(bars)
    adx = adx_t[0] if adx_t else None
    trend_mode = adx is not None and adx >= _ADX_TREND
    if trend_mode:
        owner = 0.64 * struct + 0.36 * mom            # RSI SUSAR (renormalize)
    else:
        owner = 0.50 * struct + 0.28 * mom + 0.22 * rsi_lean  # range: RSI konuşur
    return touche, _clamp(owner, -1.0, 1.0)


def _mean(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def _score_summary(aligned: list[float], hits: list[int]) -> dict:
    n = len(aligned)
    return {
        "n": n,
        "edge_pct": round(_mean(aligned), 4),
        "hit_rate": round(sum(hits) / n, 4) if n else 0.0,
    }


def _verdict(delta_edge: float, typical_move: float, n: int, *, stable: bool) -> str:
    """Owner üstünlüğü damgası: edge farkı TF-adil eşiği geçmeli + iki-yarı kararlı.

    OWNER_BETTER = owner_edge − touche_edge ≥ margin·tipik_hareket VE iki yarıda da
    owner önde. TOUCHE_BETTER = tersi. FLAT = fark önemsiz/kararsız. Az örnek → INSUFFICIENT."""
    if n < 20:
        return "INSUFFICIENT"
    margin = _EDGE_MARGIN_RATIO * typical_move if typical_move > 0 else 0.0
    if delta_edge >= margin and stable:
        return "OWNER_BETTER"
    if delta_edge <= -margin and stable:
        return "TOUCHE_BETTER"
    return "FLAT"


def analyze(symbols: list[str] | None = None, timeframes=_TIMEFRAMES) -> dict:
    """Her TF için touche vs owner yön skorunun ileri-getiri ayrımını PAIRED ölç.

    Metrik `edge_pct` = ortalama(ileri_getiri × işaret(lean)) × 100 — skoru takip
    etsen ortalama yön-getirisi. İki skor AYNI barlarda ölçülür (adil). `delta` =
    owner − touche. Owner üstünlüğü iki kronolojik yarıda da varsa `stable`."""
    syms = symbols or sorted(set(ROTATION_SYMBOLS.values()) | {"BTCUSD"})
    per_tf: dict[str, dict] = {}
    for tf in timeframes:
        H = _HORIZON.get(tf, 6)
        tou_al: list[float] = []   # touche aligned forward returns (%)
        tou_hit: list[int] = []
        own_al: list[float] = []
        own_hit: list[int] = []
        # iki-yarı kararlılık: delta (owner−touche) her yarıda
        half_delta: tuple[list[float], list[float]] = ([], [])
        # anlaşmazlık teşhisi: owner≠touche işaretli barlarda owner'ın yön-getirisi
        disagree_al: list[float] = []
        all_fwd: list[float] = []
        used_syms = 0
        for sym in syms:
            bars = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
            if len(bars) < _MIN_WARMUP + H + 1:
                continue
            if sum(1 for b in bars if b.high <= b.low) / len(bars) > _FLAT_MAX:
                continue  # fitilsiz veri (ör. anlık-fiyat kripto) — atla
            used_syms += 1
            closes_all = [b.close for b in bars]
            mid = (_MIN_WARMUP + len(bars) - H) // 2
            for i in range(_MIN_WARMUP, len(bars) - H, H):  # bindirmesiz
                base = closes_all[i]
                if not base:
                    continue
                pair = leans(closes_all[: i + 1], bars[: i + 1])
                if pair is None:
                    continue  # ikisi de hesaplanamadı → adil paired için atla
                t, o = pair
                fwd = (closes_all[i + H] - base) / base * 100.0
                all_fwd.append(fwd)
                t_dir = abs(t) > _DIR_EPS
                o_dir = abs(o) > _DIR_EPS
                if t_dir:
                    a = fwd if t > 0 else -fwd
                    tou_al.append(a)
                    tou_hit.append(1 if a > 0 else 0)
                if o_dir:
                    a = fwd if o > 0 else -fwd
                    own_al.append(a)
                    own_hit.append(1 if a > 0 else 0)
                # anlaşmazlık: ikisi de yönlü ama işaretleri zıt → owner'ın kararı
                if t_dir and o_dir and (t > 0) != (o > 0):
                    disagree_al.append(fwd if o > 0 else -fwd)
                # kararlılık: bu barda owner ve touche'un yön-getirisi farkı
                if t_dir and o_dir:
                    d = (fwd if o > 0 else -fwd) - (fwd if t > 0 else -fwd)
                    (half_delta[0] if i < mid else half_delta[1]).append(d)
        typical_move = _mean([abs(f) for f in all_fwd])
        tou_s = _score_summary(tou_al, tou_hit)
        own_s = _score_summary(own_al, own_hit)
        delta_edge = own_s["edge_pct"] - tou_s["edge_pct"]
        da, db = half_delta
        stable = bool(da and db and _mean(da) > 0 and _mean(db) > 0)
        n_paired = min(len(tou_al), len(own_al))
        per_tf[tf] = {
            "horizon_bars": H,
            "symbols_used": used_syms,
            "typical_move_pct": round(typical_move, 4),
            "touche": tou_s,
            "owner": own_s,
            "delta_edge_pct": round(delta_edge, 4),
            "delta_first_half": round(_mean(da), 4),
            "delta_second_half": round(_mean(db), 4),
            "stable": stable,
            "disagree_n": len(disagree_al),
            "disagree_owner_edge_pct": round(_mean(disagree_al), 4),
            "verdict": _verdict(delta_edge, typical_move, n_paired, stable=stable),
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": _ENGINE,
        "universe_n": len(syms),
        "per_timeframe": per_tf,
        "note": (
            "IZOLE salt-gozlem: owner'in yapi-agirlikli yon skoru (RSI rol-kisitli, "
            "ADX rejim kapisi) touche corbasina karsi AYNI barlarda ileri-getiriyle "
            "yaristirilir. OWNER_BETTER = edge farki TF-adil esigi gecer VE iki yarida "
            "tutarli. Canli skora/karara/paper'a ASLA yazmaz; touche agirliklari owner "
            "onayi olmadan DEGISMEZ."
        ),
    }


def artifact_path() -> Path:
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
    """Worker-adımı: flag AÇIK + artifact bayatsa yeniden ölç; tazeyken SKIP.
    Durum = artifact'ın kendisi (generated_at). Bozuk/eski-cetvel → yeniden üret.
    KAPALIYKEN tam no-op (import bile lazy — worker'da flag arkasında)."""
    if not enabled():
        return {"status": "DISABLED"}
    try:
        path = artifact_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            if data.get("engine") == _ENGINE and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = analyze()
    _write(rep)
    return {"status": "OK", "timeframes": list(rep["per_timeframe"])}


__all__ = ["FLAG", "analyze", "artifact_path", "enabled", "leans", "run_if_due"]
