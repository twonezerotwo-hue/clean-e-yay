"""Keşif tarayıcısı (K-1) — adaylara gölge analiz, işlem AÇMAZ.

Simülasyon canlı zincirin ÇEKİRDEĞİNİ birebir kullanır (kopya yok → sapma yok):
teknik motor `build_timeframe_result`, kalibrasyon `predict_calibrated_tf`,
EV formülü `decision.engine._expected_value` (+ aynı rr/cost config'i),
SL/TP motoru `compute_tf_targets`/`compute_fixed_targets` (lifecycle ile aynı
flag dalı). Canlı zincirden BİLİNÇLİ farklar (discovery-lite): haber/sentinel/
quantum/rotasyon modül skorları girmez (aday sembolde haber sembol-filtresi
zaten nötr kalırdı), mistake-memory girmez (yeni sembolün geçmişi yok),
portföy-durum kapıları girmez (ölçülen ANALİZ hükmü, kitap durumu değil).
Rejim etiketi canlı snapshot store'dan okunur (yoksa NEUTRAL).

v1 kuralları (owner 2026-07-04): LONG-only; sinyal için 1d bullish + en az
2 TF bullish (üst dilim onayı — htf_alignment ruhu); kalibre güven
`consensus.min_open_confidence` tabanının üstünde; EV pozitif.

Artifact: data/runtime/discovery_scan.json (env DISCOVERY_SCAN_PATH).
Kota: koşu başına `scan.per_run` aday, round-robin cursor — tik'e sıfır etki
(learning worker'da koşar), kripto OHLCV yalnız kısa liste için çekilir.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

from packages.data import snapshot_store
from packages.data.providers import ohlcv
from packages.data.providers.ohlcv import coingecko as cg_ohlcv
from packages.data.providers.ohlcv import resample
from packages.data.providers.technical.timeframe import build_timeframe_result
from packages.data.registry.loader import CONFIG_DIR, load_thresholds
from packages.data.types import OHLCVBar
from packages.decision import engine as decision_engine
from packages.learning import empirical_pwin
from packages.learning.calibration_store import (
    predict_calibrated_tf,
    raw_confidence_from_score,
)
from packages.risk.trade_economics import (
    compute_fixed_targets,
    compute_tf_targets,
    tf_targets_enabled,
)

TFS = ("1h", "4h", "1d")
_TF_ORDER = {"1h": 0, "4h": 1, "1d": 2}
_RESULTS_CAP = 100

BarsFn = Callable[[str, str], list[OHLCVBar]]
CryptoBarsFn = Callable[[str, str, str], list[OHLCVBar] | None]  # (cg_id, symbol, tf)


def _out_path() -> Path:
    return Path(os.environ.get("DISCOVERY_SCAN_PATH", "data/runtime/discovery_scan.json"))


def load_config() -> dict:
    path = CONFIG_DIR / "discovery.yaml"
    try:
        return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except OSError:
        return {}


def _load_artifact() -> dict:
    path = _out_path()
    try:
        if path.exists():
            return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def _regime_label() -> str:
    """Canlı tick'in son rejim etiketi (snapshot store viewmodel'ından).
    Yoksa NEUTRAL — empirical_pwin tablosunda en dolu satır da odur."""
    try:
        latest = snapshot_store.latest() or {}
        label = str(((latest.get("decision_matrix") or {}).get("regime")) or "")
        return label or "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def _candidate_bars(
    cand: dict, tf: str, *, get_bars: BarsFn, fetch_crypto: CryptoBarsFn
) -> list[OHLCVBar]:
    """ETF → OHLCV orchestrator (cache'li); kripto → fetch_by_ticker (TTL
    throttle'lı; 4h yerelde 1h'ten resample — ek çağrı yok)."""
    if cand.get("kind") == "crypto":
        cg_id, sym = str(cand.get("cg_id") or ""), str(cand["symbol"])
        if not cg_id:
            return []
        if tf == "4h":
            base = fetch_crypto(cg_id, sym, "1h") or []
            return resample.resample(base, "4h")
        return fetch_crypto(cg_id, sym, tf) or []
    return get_bars(cand["symbol"], tf)


def _analyze(
    cand: dict,
    *,
    regime_label: str,
    min_bars: int,
    get_bars: BarsFn,
    fetch_crypto: CryptoBarsFn,
    now: datetime,
) -> dict:
    symbol = str(cand["symbol"])
    th = load_thresholds()
    cons_th = th.get("consensus") or {}
    bullish_min = float(cons_th.get("bullish_min", 55))
    min_conf = float(cons_th.get("min_open_confidence", 0.0))

    per_tf: dict[str, dict] = {}
    for tf in TFS:
        bars = [b for b in _candidate_bars(cand, tf, get_bars=get_bars, fetch_crypto=fetch_crypto) if b.verified]
        if len(bars) < min_bars:
            per_tf[tf] = {"status": "NO_DATA", "bars": len(bars)}
            continue
        tr = build_timeframe_result(symbol, tf, bars)
        per_tf[tf] = {
            "status": tr.status,
            "bars": len(bars),
            "direction_score": tr.score_overview.direction_score,
            "atr": tr.key_levels.atr,
            "last_close": bars[-1].close,
        }

    result = {
        "symbol": symbol,
        "kind": cand.get("kind", "crypto"),
        "checked_at": now.isoformat(),
        "regime": regime_label,
        "per_tf": per_tf,
        "verdict": "NO_SIGNAL",
        "reasons": [],
    }

    bullish = [
        tf for tf in TFS
        if (per_tf[tf].get("direction_score") or 0) >= bullish_min
    ]
    # v1: LONG-only + üst dilim onayı — 1d bullish ŞART, toplam ≥2 TF bullish.
    if "1d" not in bullish:
        result["reasons"].append("htf_1d_not_bullish")
        return result
    if len(bullish) < 2:
        result["reasons"].append("single_tf_only")
        return result

    entry_tf = min(bullish, key=lambda t: _TF_ORDER[t])
    score = float(per_tf[entry_tf]["direction_score"])
    raw = raw_confidence_from_score(score)
    cal, conf_source = predict_calibrated_tf(raw, entry_tf)
    if cal < min_conf:
        result["reasons"].append(f"below_min_open_confidence({cal:.2f}<{min_conf})")
        return result

    # EV — canlı motorla AYNI formül/config (kopya değil, aynı fonksiyon).
    rr = decision_engine._tf_rr(entry_tf)
    ev_cfg = decision_engine._ev_gate_cfg()
    cost_r = float(ev_cfg.get("cost_r", 0.1))
    emp = empirical_pwin.lookup(entry_tf, regime_label)
    p_for_ev = emp.p_win if (emp is not None and empirical_pwin.enabled()) else cal
    ev = decision_engine._expected_value(p_for_ev, rr, cost_r)
    if ev < 0:
        result["reasons"].append(f"negative_ev({ev:.3f}R,p={p_for_ev:.2f})")
        return result

    entry = float(per_tf[entry_tf]["last_close"])
    atr = per_tf[entry_tf].get("atr")
    # SL/TP: lifecycle ile aynı flag dalı (tf_targets açıksa TF-aware motor).
    if tf_targets_enabled():
        targets = compute_tf_targets(
            symbol, "long", entry, timeframe=entry_tf, atr=atr,
            predicted_confidence=cal,
        )
    else:
        targets = compute_fixed_targets(symbol, "long", entry, predicted_confidence=cal)

    result.update({
        "verdict": "WOULD_OPEN_LONG",
        "entry_timeframe": entry_tf,
        "entry": round(entry, 6),
        "sl": targets.sl,
        "tp": targets.tp,
        "rr": targets.rr,
        "direction_score": score,
        "confidence": round(cal, 4),
        "confidence_source": conf_source,
        "expected_value": round(ev, 4),
        "p_source": "empirical" if (emp is not None and empirical_pwin.enabled()) else "calibrated",
        "bullish_tfs": bullish,
    })
    return result


def run_if_due(
    now: datetime | None = None,
    *,
    fetch_json=None,
    get_bars: BarsFn | None = None,
    fetch_crypto_bars: CryptoBarsFn | None = None,
) -> dict:
    """Learning worker adımı: interval dolmadıysa CACHED; dolduysa kota kadar
    adayı round-robin analiz edip artifact'ı günceller."""
    from packages.discovery import universe  # döngüsel import'u önle (aynı paket)

    now = now or datetime.now(UTC)
    cfg = load_config()
    scan_cfg = dict(cfg.get("scan") or {})
    crypto_cfg = dict(cfg.get("crypto") or {})
    interval = int(scan_cfg.get("interval_sec", 900))
    per_run = int(scan_cfg.get("per_run", 5))
    min_bars = int(scan_cfg.get("min_bars", 60))

    prev = _load_artifact()
    gen_raw = str(prev.get("generated_at") or "")
    if gen_raw:
        try:
            age = (now - datetime.fromisoformat(gen_raw)).total_seconds()
            if 0 <= age < interval:
                return {"status": "CACHED", "age_sec": int(age)}
        except ValueError:
            pass

    # Kripto kısa listesi: markets_ttl_sec içinde önceki liste yeniden kullanılır
    # (API bütçesi); süresi dolduysa TEK markets çağrısı.
    markets_ttl = int(crypto_cfg.get("markets_ttl_sec", 3600))
    crypto_uni = dict(prev.get("crypto_universe") or {})
    fetched_raw = str(crypto_uni.get("fetched_at") or "")
    reuse = False
    if fetched_raw and crypto_uni.get("status") == "OK":
        try:
            reuse = 0 <= (now - datetime.fromisoformat(fetched_raw)).total_seconds() < markets_ttl
        except ValueError:
            reuse = False
    if not reuse:
        crypto_uni = universe.crypto_shortlist(crypto_cfg, fetch_json=fetch_json)

    sector_cands = universe.sector_candidates()
    crypto_cands = [
        {**c, "kind": "crypto"} for c in (crypto_uni.get("candidates") or [])
    ]
    candidates = sector_cands + crypto_cands

    regime_label = _regime_label()
    results = dict(prev.get("results") or {})
    scanned: list[str] = []
    if candidates:
        cursor = int(prev.get("cursor") or 0) % len(candidates)
        fetch_crypto = fetch_crypto_bars or cg_ohlcv.fetch_by_ticker
        bars_fn = get_bars or ohlcv.get_bars
        for i in range(min(per_run, len(candidates))):
            cand = candidates[(cursor + i) % len(candidates)]
            res = _analyze(
                cand, regime_label=regime_label, min_bars=min_bars,
                get_bars=bars_fn, fetch_crypto=fetch_crypto, now=now,
            )
            results[str(cand["symbol"])] = res
            scanned.append(str(cand["symbol"]))
        cursor = (cursor + len(scanned)) % len(candidates)
    else:
        cursor = 0

    # results haritasını sınırla (en yeni checked_at kalır — artifact şişmez).
    if len(results) > _RESULTS_CAP:
        keep = sorted(results.values(), key=lambda r: str(r.get("checked_at")))[-_RESULTS_CAP:]
        results = {str(r["symbol"]): r for r in keep}

    signals = [r for r in results.values() if r.get("verdict") == "WOULD_OPEN_LONG"]
    artifact = {
        "generated_at": now.isoformat(),
        "engine": "discovery_lite_v1",
        "regime": regime_label,
        "cursor": cursor,
        "crypto_universe": crypto_uni,
        "rising_sectors": sector_cands,
        "results": results,
        "signal_symbols": sorted(str(s["symbol"]) for s in signals),
    }
    path = _out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")

    return {
        "status": "OK",
        "candidates_total": len(candidates),
        "scanned": scanned,
        "signals_n": len(signals),
        "cursor": cursor,
    }
