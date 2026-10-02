"""Y-6 — Haber olay-çalışması (event study), SHADOW-ONLY / SALT-GÖZLEM.

Soru: haberin bir edge'i var mı? Yani "bullish damgalı X kaynağı haberi"
sonrası fiyat N bar boyunca gerçekten yukarı mı gidiyor, yoksa gürültü mü?
Kanıt çıkmazsa DÜRÜST sonuç: "news ağırlığı kanıtsız" — challenger'a news
görünürlüğü ancak bucket gerçekten öngörü gösterirse anlam taşır.

Tarihsel haber arşivi YOK → kanıt (bar arşivi felsefesi) ZAMANLA birikir:
- `record_events()` off-tick her döngüde o anki VERIFIED başlıkları damgalı
  deftere ekler (id ile dedupe; asset_impact yönü taşıyanlar).
- `compute()` off-tick olgunlaşan olaylar için (N bar geçmiş) ileri-getiriyi
  `ohlcv.history` REUSE ile ölçer → (kaynak × sentiment) kovası karnesi.

SALT-GÖZLEM: hiçbir çıktı karara/ağırlığa/boyuta dokunmaz. Aktivasyon (news
görünürlüğünü challenger'a vermek) AYRI owner kararı; bu modül yalnız kanıt
üretir. Config-flag YOK (ölü-flag yasağı) — sürekli gözlem, off-tick, ucuz.
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds
from packages.ops.store import write_text_atomic

_LEDGER_MAX_MB = 32
_HORIZON_DEFAULT = 5
_TF_DEFAULT = "1d"
_MIN_BUCKET_N_DEFAULT = 8
_CAUSAL_LEDGER_MAX_MB = 32


def _cfg() -> dict:
    try:
        return load_thresholds().get("news_event_study") or {}
    except (OSError, KeyError, ValueError, TypeError):
        return {}


def _ledger_path() -> Path:
    return Path(os.environ.get(
        "NEWS_EVENT_LEDGER_PATH", "data/runtime/news_event_ledger.jsonl"))


def _table_path() -> Path:
    return Path(os.environ.get(
        "NEWS_EVENT_STUDY_PATH", "data/runtime/news_event_study.json"))


# ── off-tick: haber olaylarını damgala (dedupe, boyut-tavanlı) ─────────────────

def _known_ids(p: Path) -> set[str]:
    ids: set[str] = set()
    try:
        if not p.exists():
            return ids
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                ids.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue
    except OSError:
        return ids
    return ids


def record_events(headlines=None, now: datetime | None = None) -> int:
    """O anki VERIFIED + yönlü başlıkları deftere ekle (id ile dedupe).

    Yeni-satır sayısını döndürür. Asla fırlatmaz; defter tavanı aşılırsa yazmaz
    (tik şişen dosyaya kilitlenmez). Yönsüz/nötr (asset_impact boş) haber öngörü
    testine giremez → deftere de girmez."""
    now = now or datetime.now(UTC)
    if headlines is None:
        from packages.data.providers import news
        headlines = news.list_headlines(limit=40)
    p = _ledger_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > _LEDGER_MAX_MB * 1024 * 1024:
            return 0
        known = _known_ids(p)
        rows: list[str] = []
        for h in headlines:
            hid = getattr(h, "id", None)
            if not hid or hid in known or not getattr(h, "verified", False):
                continue
            impact = {s: float(d) for s, d in (getattr(h, "asset_impact", {}) or {}).items()
                      if float(d) != 0.0}
            if not impact:
                continue  # yönsüz haber → öngörü testine girmez
            known.add(hid)
            ts = getattr(h, "ts", None)
            rows.append(json.dumps({
                "id": hid,
                "source": getattr(h, "source", "?") or "?",
                "sentiment": getattr(h, "sentiment", None) or "neutral",
                "ts": (ts.isoformat() if hasattr(ts, "isoformat") else str(ts)),
                "symbols": impact,
                "recorded_at": now.isoformat(),
            }, ensure_ascii=False))
        if rows:
            with p.open("a", encoding="utf-8") as f:
                f.write("\n".join(rows) + "\n")
        return len(rows)
    except Exception:  # gözlem kaydı asla worker'ı düşürmez
        return 0


# ── off-tick: ileri-getiri karnesi (ohlcv.history REUSE) ───────────────────────

def _read_ledger() -> list[dict]:
    out: list[dict] = []
    try:
        p = _ledger_path()
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return out
    return out


def _forward_return_pct(bars, event_ts: datetime, horizon: int) -> float | None:
    """Olaydan SONRAKİ ilk bara göre N-bar ileri kapanış getirisi (%).

    Olgunlaşmamış (N bar henüz oluşmamış) veya baz kapanış 0 → None (uydurma
    yok — kanıt yalnız gerçekleşmiş barlardan)."""
    idx = None
    for i, b in enumerate(bars):
        if b.ts >= event_ts:
            idx = i
            break
    if idx is None or idx + horizon >= len(bars):
        return None
    base = bars[idx].close
    if not base:
        return None
    return (bars[idx + horizon].close / base - 1.0) * 100.0


def compute(events=None, now: datetime | None = None) -> dict:
    """(kaynak × sentiment) kovası: N-bar ileri-getiri + yön-isabet karnesi.

    hit = ileri-getiri işareti haberin yönüyle uyuşuyor. n<min → INSUFFICIENT
    (kanıtsız). Global dürüst hüküm: hiçbir kova öngörü göstermezse
    'news ağırlığı kanıtsız'."""
    now = now or datetime.now(UTC)
    cfg = _cfg()
    horizon = int(cfg.get("horizon_bars", _HORIZON_DEFAULT))
    tf = str(cfg.get("timeframe", _TF_DEFAULT))
    min_n = int(cfg.get("min_bucket_n", _MIN_BUCKET_N_DEFAULT))
    if events is None:
        events = _read_ledger()

    from packages.data.providers.ohlcv import get_bars, history
    bars_cache: dict[str, list] = {}

    def _bars(sym: str):
        if sym not in bars_cache:
            try:
                bars_cache[sym] = history.merged(history.load(sym, tf), get_bars(sym, tf) or [])
            except Exception:
                bars_cache[sym] = []
        return bars_cache[sym]

    buckets: dict[str, dict] = {}
    matured = 0
    pending = 0
    for ev in events:
        try:
            ets = datetime.fromisoformat(str(ev.get("ts")))
        except (ValueError, TypeError):
            continue
        if ets.tzinfo is None:
            ets = ets.replace(tzinfo=UTC)
        sentiment = str(ev.get("sentiment") or "neutral")
        source = str(ev.get("source") or "?")
        for sym, direction in (ev.get("symbols") or {}).items():
            d = float(direction)
            if d == 0.0:
                continue
            fwd = _forward_return_pct(_bars(sym), ets, horizon)
            if fwd is None:
                pending += 1
                continue
            matured += 1
            key = f"{source}|{sentiment}"
            b = buckets.setdefault(key, {"n": 0, "hits": 0, "sum_dir_return": 0.0})
            b["n"] += 1
            # yön-hizalı getiri: haber yukarı diyorsa +getiri iyi, aşağı diyorsa −
            dir_return = fwd if d > 0 else -fwd
            b["sum_dir_return"] += dir_return
            if dir_return > 0:
                b["hits"] += 1

    predictive = 0
    for b in buckets.values():
        n = b["n"]
        b["avg_dir_return_pct"] = round(b["sum_dir_return"] / n, 4) if n else 0.0
        b["hit_rate"] = round(b["hits"] / n, 3) if n else None
        b["sum_dir_return"] = round(b["sum_dir_return"], 4)
        if n >= min_n and (b["hit_rate"] or 0) > 0.5 and b["avg_dir_return_pct"] > 0:
            b["verdict"] = "PREDICTIVE"
            predictive += 1
        elif n >= min_n:
            b["verdict"] = "NO_EDGE"
        else:
            b["verdict"] = "INSUFFICIENT"

    table = {
        "generated_at": now.isoformat(),
        "engine": "news_event_study_v1",
        "horizon_bars": horizon,
        "timeframe": tf,
        "events_total": len(events),
        "matured": matured,
        "pending": pending,
        "buckets": dict(sorted(buckets.items())),
        "global_verdict": "PREDICTIVE" if predictive else "UNPROVEN",
        "note": "SALT-GOZLEM: karara/agirliga dokunmaz; news gorunurlugu ayri owner karari",
    }
    p = _table_path()
    write_text_atomic(p, json.dumps(table, ensure_ascii=False, indent=1))
    return table


# ── endpoint yüzeyi ────────────────────────────────────────────────────────────

def _load_table() -> dict | None:
    try:
        p = _table_path()
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def viewmodel() -> dict:
    """GET /learning/news-event-study — kova karnesi + dürüst global hüküm."""
    table = _load_table()
    return {
        "status": "OK" if table else "NO_TABLE",
        "generated_at": (table or {}).get("generated_at"),
        "horizon_bars": (table or {}).get("horizon_bars", _HORIZON_DEFAULT),
        "events_total": (table or {}).get("events_total", 0),
        "matured": (table or {}).get("matured", 0),
        "pending": (table or {}).get("pending", 0),
        "buckets": (table or {}).get("buckets") or {},
        "global_verdict": (table or {}).get("global_verdict", "UNPROVEN"),
        "config": {"min_bucket_n": int(_cfg().get("min_bucket_n", _MIN_BUCKET_N_DEFAULT))},
        "shadow_only": True,
    }


# ── causal shadow observation (same learning infrastructure, no auto-promotion) ─

def _causal_ledger_path() -> Path:
    return Path(os.environ.get(
        "CAUSAL_EVENT_LEDGER_PATH", "data/runtime/causal_event_ledger.jsonl"
    ))


def _causal_study_path() -> Path:
    return Path(os.environ.get(
        "CAUSAL_EVENT_STUDY_PATH", "data/runtime/causal_event_study.json"
    ))


def record_causal_events(events, now: datetime | None = None) -> int:
    """Persist causal predictions once per event id.

    This is an observation ledger only. It accepts the serialisable
    ``GeopoliticalEvent``/``AssetImpact`` shapes produced by PR #56 or plain
    dictionaries, and never changes graph weights or decisions.
    """
    now = now or datetime.now(UTC)
    path = _causal_ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _CAUSAL_LEDGER_MAX_MB * 1024 * 1024:
            return 0
        known = _known_ids(path)
        rows: list[str] = []
        for event in events or []:
            item = event if isinstance(event, dict) else event.to_dict()
            event_id = str(item.get("event_id") or item.get("id") or "")
            if not event_id or event_id in known:
                continue
            known.add(event_id)
            rows.append(json.dumps({
                "id": event_id,
                "event_id": event_id,
                "ts": item.get("published_at") or item.get("ts") or now.isoformat(),
                "event_type": item.get("event_type", "UNKNOWN"),
                "region": item.get("region"),
                "channels": item.get("channels") or {},
                "asset_predictions": item.get("asset_predictions") or {},
                "factor_predictions": item.get("factor_predictions") or item.get("channels") or {},
                "factor_outcomes": item.get("factor_outcomes") or {},
                "asset_outcomes": item.get("asset_outcomes") or {},
                "causal_path": item.get("causal_path") or [],
                "root_event_ids": item.get("root_event_ids") or [event_id],
                "regime": item.get("regime"),
                "horizon": item.get("horizon"),
                "prediction_confidence": item.get("prediction_confidence"),
                "attribution_method": item.get("attribution_method", "event_marginal_v1"),
                "evidence": item.get("evidence") or [],
                "recorded_at": now.isoformat(),
            }, ensure_ascii=False))
        if rows:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(rows) + "\n")
        return len(rows)
    except Exception:
        return 0


def _read_causal_ledger() -> list[dict]:
    path = _causal_ledger_path()
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, TypeError):
        return []


def _causal_bucket(rows: list[tuple[float, float]], min_n: int) -> dict:
    directional = [pred * actual for pred, actual in rows]
    hits = [value for value in directional if value > 0]
    n = len(rows)
    avg = sum(directional) / n if n else None
    median = statistics.median(directional) if directional else None
    hit_rate = len(hits) / n if n else None
    verdict = "INSUFFICIENT" if n < min_n else "PREDICTIVE" if (hit_rate or 0) > 0.5 and (avg or 0) > 0 else "NO_EDGE"
    return {
        "n": n,
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "avg_directional_return": round(avg, 4) if avg is not None else None,
        "median_directional_return": round(median, 4) if median is not None else None,
        "confidence": round(min(1.0, n / max(1, min_n)), 4),
        "verdict": verdict,
    }


def causal_event_study(
    events=None,
    *,
    forward_returns: dict | None = None,
    horizons: tuple[str, ...] = ("1h", "4h", "1d"),
    min_n: int = 8,
    now: datetime | None = None,
) -> dict:
    """Build event/channel/asset/horizon evidence without promotion.

    ``forward_returns`` is an optional deterministic test/offline input. In
    production, callers may supply it from the existing OHLCV history layer;
    absent returns are kept pending rather than fabricated.
    """
    now = now or datetime.now(UTC)
    rows = list(events if events is not None else _read_causal_ledger())
    returns = forward_returns or {}
    bars_cache: dict[tuple[str, str], list] = {}

    def _ohlcv_return(asset: str, event_ts: datetime, horizon: str) -> float | None:
        # Use only bars strictly after the event timestamp.  No prediction is
        # scored until the requested post-event bar actually exists.
        tf = "1d" if horizon == "1d" else "1h"
        key = (asset, tf)
        if key not in bars_cache:
            try:
                from packages.data.providers.ohlcv import get_bars, history
                bars_cache[key] = history.merged(history.load(asset, tf), get_bars(asset, tf) or [])
            except Exception:
                bars_cache[key] = []
        bars = bars_cache[key]
        steps = {"1h": 1, "4h": 4, "1d": 1}.get(horizon, 1)
        return _forward_return_pct(bars, event_ts, steps)
    buckets: dict[str, list[tuple[float, float]]] = {}
    factor_rows: list[dict] = []
    pending = 0
    for event in rows:
        predictions = event.get("asset_predictions") or {}
        channels = event.get("channels") or {}
        if isinstance(channels, list):
            channels = {channel: 1.0 for channel in channels}
        event_type = str(event.get("event_type") or "UNKNOWN")
        region = str(event.get("region") or "UNKNOWN")
        factor_predictions = event.get("factor_predictions") or channels
        factor_outcomes = event.get("factor_outcomes") or {}
        for path in event.get("causal_path") or []:
            if not isinstance(path, dict):
                continue
            source = str(path.get("source") or "")
            target = str(path.get("target") or "")
            predicted = factor_predictions.get(source)
            actual = factor_outcomes.get(target)
            if predicted is not None and actual is not None:
                factor_rows.append({
                    "edge": f"{source}->{target}",
                    "source_value": predicted,
                    "target_response": actual,
                    "regime": event.get("regime"),
                    "horizon": event.get("horizon"),
                    "prior_strength": path.get("weight", 0.5),
                })
        for asset, prediction in predictions.items():
            try:
                direction = float(prediction)
            except (TypeError, ValueError):
                continue
            for horizon in horizons:
                actual = (returns.get((event.get("event_id") or event.get("id"), asset, horizon))
                          if returns else None)
                if actual is None and not returns:
                    try:
                        event_ts = datetime.fromisoformat(str(event.get("ts") or now.isoformat()))
                        if event_ts.tzinfo is None:
                            event_ts = event_ts.replace(tzinfo=UTC)
                        actual = _ohlcv_return(str(asset), event_ts, horizon)
                    except (TypeError, ValueError):
                        actual = None
                if actual is None:
                    pending += 1
                    continue
                for channel in channels or {"aggregate": 1.0}:
                    key = f"{event_type}|{region}|{channel}|{asset}|{horizon}"
                    buckets.setdefault(key, []).append((direction, float(actual)))
    factor_calibration = (
        __import__("packages.learning.causal_calibration", fromlist=["calibrate_edges"]).calibrate_edges(factor_rows, min_samples=min_n)
        if factor_rows else {"status": "INSUFFICIENT", "recommendations": {}, "shadow_only": True, "auto_apply": False}
    )
    if factor_rows:
        try:
            __import__("packages.learning.causal_calibration", fromlist=["write_recommendations"]).write_recommendations(factor_rows)
        except Exception:
            pass
    table = {
        "generated_at": now.isoformat(),
        "engine": "causal_event_study_v1",
        "events_total": len(rows),
        "pending": pending,
        "buckets": {key: _causal_bucket(values, min_n) for key, values in sorted(buckets.items())},
        "factor_calibration": factor_calibration,
        "shadow_only": True,
        "auto_promotion": False,
    }
    try:
        path = _causal_study_path()
        write_text_atomic(path, json.dumps(table, ensure_ascii=False, indent=1))
    except OSError:
        pass
    return table


def causal_backtest(rows, *, min_n: int = 8) -> dict:
    """Compare causal and legacy directional evidence without look-ahead."""
    by_asset: dict[str, dict[str, int]] = {}
    divergences = 0
    causal_correct_when_legacy_wrong = 0
    legacy_correct_when_causal_wrong = 0
    for row in rows or []:
        asset = str(row.get("asset", "UNKNOWN"))
        causal = float(row.get("causal_direction", 0.0))
        legacy = float(row.get("legacy_direction", 0.0))
        forward = float(row.get("forward_return", 0.0))
        causal_hit = causal * forward > 0
        legacy_hit = legacy * forward > 0
        stats = by_asset.setdefault(asset, {"n": 0, "causal_hits": 0, "legacy_hits": 0})
        stats["n"] += 1
        stats["causal_hits"] += int(causal_hit)
        stats["legacy_hits"] += int(legacy_hit)
        if (causal > 0) != (legacy > 0):
            divergences += 1
            causal_correct_when_legacy_wrong += int(causal_hit and not legacy_hit)
            legacy_correct_when_causal_wrong += int(legacy_hit and not causal_hit)
    for stats in by_asset.values():
        stats["causal_hit_rate"] = round(stats["causal_hits"] / stats["n"], 4) if stats["n"] else None
        stats["legacy_hit_rate"] = round(stats["legacy_hits"] / stats["n"], 4) if stats["n"] else None
        stats["verdict"] = "INSUFFICIENT" if stats["n"] < min_n else "OBSERVE"
    return {
        "by_asset": by_asset,
        "divergence_count": divergences,
        "causal_correct_when_legacy_wrong": causal_correct_when_legacy_wrong,
        "legacy_correct_when_causal_wrong": legacy_correct_when_causal_wrong,
        "shadow_only": True,
        "auto_promotion": False,
    }


def causal_historical_evaluator(rows, *, min_n: int = 8) -> dict:
    """Evaluate timestamped, already-materialised evidence without look-ahead.

    The caller supplies one row per event/snapshot with values that were
    available at that timestamp and a *post-event* forward return.  This keeps
    the replay deterministic and lets the existing snapshot/backtest loaders
    provide the data without creating a second provider.  Future fields are
    accepted only as scoring outcomes.
    """
    dimensions = {"by_asset": {}, "by_timeframe": {}, "by_regime": {}, "by_event_type": {}}
    ignored_future_rows = 0
    for row in rows or []:
        # A row may carry event timestamps separately.  Future evidence is
        # rejected before scoring; the forward return itself is outcome-only.
        as_of = row.get("as_of") or row.get("snapshot_as_of") or row.get("timestamp")
        event_ts = row.get("event_ts") or row.get("published_at")
        skip_row = False
        if as_of and event_ts:
            try:
                as_of_dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                event_dt = datetime.fromisoformat(str(event_ts).replace("Z", "+00:00"))
                if as_of_dt.tzinfo is None:
                    as_of_dt = as_of_dt.replace(tzinfo=UTC)
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=UTC)
                if event_dt > as_of_dt:
                    ignored_future_rows += 1
                    skip_row = True
            except (TypeError, ValueError):
                ignored_future_rows += 1
                skip_row = True
        # Optional provenance fields let replay callers prove that ingestion
        # and publication were also as-of, not merely event timestamps.
        for field in ("published_at", "ingested_at", "consensus_as_of"):
            value = row.get(field)
            if value and as_of:
                try:
                    value_dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    asof_dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                    if value_dt.tzinfo is None:
                        value_dt = value_dt.replace(tzinfo=UTC)
                    if asof_dt.tzinfo is None:
                        asof_dt = asof_dt.replace(tzinfo=UTC)
                    if value_dt > asof_dt:
                        ignored_future_rows += 1
                        skip_row = True
                        break
                except (TypeError, ValueError):
                    ignored_future_rows += 1
                    skip_row = True
                    break
        if skip_row:
            continue
        try:
            causal = float(row.get("causal_direction", 0.0))
            legacy = float(row.get("legacy_direction", 0.0))
            forward = float(row["forward_return"])
        except (KeyError, TypeError, ValueError):
            continue
        keys = {
            "by_asset": str(row.get("asset", "UNKNOWN")),
            "by_timeframe": str(row.get("timeframe", "UNKNOWN")),
            "by_regime": str(row.get("regime", "UNKNOWN")),
            "by_event_type": str(row.get("event_type", "UNKNOWN")),
        }
        for dimension, key in keys.items():
            bucket = dimensions[dimension].setdefault(key, {"n": 0, "causal_hits": 0, "legacy_hits": 0, "false_positives": 0, "abstentions": 0, "sum_forward_return": 0.0, "divergence_count": 0, "causal_correct_when_legacy_wrong": 0, "legacy_correct_when_causal_wrong": 0})
            causal_hit = causal * forward > 0
            legacy_hit = legacy * forward > 0
            bucket["n"] += 1
            bucket["causal_hits"] += int(causal_hit)
            bucket["legacy_hits"] += int(legacy_hit)
            bucket["false_positives"] += int(causal != 0 and not causal_hit)
            bucket["abstentions"] += int(causal == 0)
            bucket["sum_forward_return"] += forward
            bucket["divergence_count"] += int((causal > 0) != (legacy > 0))
            bucket["causal_correct_when_legacy_wrong"] += int(causal_hit and not legacy_hit)
            bucket["legacy_correct_when_causal_wrong"] += int(legacy_hit and not causal_hit)
    for group in dimensions.values():
        for bucket in group.values():
            n = bucket["n"]
            bucket.update({
                "causal_hit_rate": round(bucket["causal_hits"] / n, 4) if n else None,
                "legacy_hit_rate": round(bucket["legacy_hits"] / n, 4) if n else None,
                "avg_forward_return": round(bucket["sum_forward_return"] / n, 4) if n else None,
                "false_positive_rate": round(bucket["false_positives"] / n, 4) if n else None,
                "abstention_rate": round(bucket["abstentions"] / n, 4) if n else None,
                "verdict": "INSUFFICIENT" if n < min_n else "OBSERVE",
            })
            bucket.pop("sum_forward_return", None)
    return {**dimensions, "status": "HISTORICAL_EVALUATOR", "samples": sum(item.get("n", 0) for group in dimensions.values() for item in group.values()), "future_rows_ignored": ignored_future_rows, "shadow_only": True, "auto_promotion": False}


def _snapshot_from_reconstruction(row: dict, payload: dict, as_of: datetime):
    """Decode a compact historical MarketSnapshot input and enforce as-of T."""
    from packages.data.ingestion.pipeline import MarketSnapshot
    from packages.data.quality.dqs import QualityReport
    from packages.data.types import (
        Catalyst,
        CatalystImpact,
        DerivativesSnapshot,
        NewsHeadline,
        OptionsSnapshot,
        PriceQuote,
        RotationView,
        TechnicalSnapshot,
        VolatilitySnapshot,
    )

    def _before(items: list[dict], field: str = "ts") -> list[dict]:
        kept: list[dict] = []
        for item in items or []:
            raw = item.get(field)
            try:
                timestamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
                if timestamp is not None and timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                if timestamp is None or timestamp <= as_of:
                    kept.append(item)
            except (TypeError, ValueError):
                continue
        return kept

    def _decode(value: object, model):
        if not isinstance(value, dict):
            return None
        raw = value.get("ts")
        # These normalized positioning/evidence models carry a timestamp in
        # the runtime contract.  Do not let a Pydantic default_factory invent
        # one while replaying an old/incomplete payload.
        if not raw:
            return None
        if raw:
            try:
                timestamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                if timestamp > as_of:
                    return None
            except (TypeError, ValueError):
                return None
        try:
            return model(**value)
        except (TypeError, ValueError):
            return None

    def _decode_map(value: object, model) -> dict:
        result: dict = {}
        if not isinstance(value, dict):
            return result
        for key, item in value.items():
            decoded = _decode(item, model)
            if decoded is not None:
                result[str(key)] = decoded
        return result

    def _decode_nested_map(value: object, model) -> dict:
        result: dict = {}
        if not isinstance(value, dict):
            return result
        for key, items in value.items():
            decoded = _decode_map(items, model)
            if decoded:
                result[str(key)] = decoded
        return result

    prices = [PriceQuote(**item) for item in _before(payload.get("prices") or [])]
    headlines = [NewsHeadline(**item) for item in _before(payload.get("headlines") or [])]
    catalysts = [Catalyst(**item) for item in _before(payload.get("catalysts") or [])]
    catalyst_impacts = [item for item in (_decode(item, CatalystImpact) for item in payload.get("catalyst_impacts") or []) if item is not None]
    technicals = {
        symbol: TechnicalSnapshot(**value)
        for symbol, value in (payload.get("technicals") or {}).items()
        if isinstance(value, dict)
    }
    rotation = RotationView(**(payload.get("rotation") or {}))
    quality = QualityReport(
        score=float((payload.get("quality") or {}).get("score", 0.0)),
        freshness=float((payload.get("quality") or {}).get("freshness", 0.0)),
        completeness=float((payload.get("quality") or {}).get("completeness", 0.0)),
        drift=float((payload.get("quality") or {}).get("drift", 0.0)),
        reconciliation=float((payload.get("quality") or {}).get("reconciliation", 0.0)),
        decision_usage=float((payload.get("quality") or {}).get("decision_usage", 0.0)),
        status=str((payload.get("quality") or {}).get("status", "DEGRADED")),
    )
    return MarketSnapshot(
        snapshot_id=str(payload.get("snapshot_id") or row.get("snapshot_id") or "historical"),
        generated_at=as_of,
        prices=prices,
        technicals=technicals,
        headlines=headlines,
        catalysts=catalysts,
        rotation=rotation,
        quality=quality,
        warnings=list(payload.get("warnings") or []),
        provider_status=dict(payload.get("provider_status") or {}),
        technicals_by_tf=payload.get("technicals_by_tf"),
        derivatives=_decode_map(payload.get("derivatives"), DerivativesSnapshot),
        volatility=_decode_nested_map(payload.get("volatility"), VolatilitySnapshot),
        options=_decode_map(payload.get("options"), OptionsSnapshot),
        catalyst_impacts=catalyst_impacts,
        flow_observations=_before(payload.get("flow_observations") or [], field="timestamp"),
        market_data_as_of=row.get("market_data_as_of"),
        events_available_as_of=row.get("events_available_as_of"),
        statements_available_as_of=row.get("statements_available_as_of"),
        macro_available_as_of=row.get("macro_available_as_of"),
        expectations_as_of=row.get("expectations_as_of"),
        flow_available_as_of=row.get("flow_available_as_of"),
        ingested_at=row.get("ingested_at"),
        provenance_domains=dict(payload.get("provenance_domains") or row.get("provenance_domains") or {}),
    )


_REPLAY_DOMAINS = {
    "market": "market_data_as_of",
    "events": "events_available_as_of",
    "statements": "statements_available_as_of",
    "macro": "macro_available_as_of",
    "expectations": "expectations_as_of",
    "flow": "flow_available_as_of",
}


def _replay_provenance_gaps(row: dict, as_of: str | None) -> tuple[list[str], bool]:
    """Apply AVAILABLE/UNAVAILABLE/UNKNOWN replay eligibility semantics."""
    domains = row.get("provenance_domains")
    domains = domains if isinstance(domains, dict) else {}
    missing: list[str] = []
    future = False
    for domain, field in _REPLAY_DOMAINS.items():
        entry = domains.get(domain)
        explicit = isinstance(entry, dict) and entry.get("status")
        status = str(entry.get("status")).upper() if explicit else ("AVAILABLE" if row.get(field) else "UNKNOWN")
        raw = (entry or {}).get("as_of") if isinstance(entry, dict) else None
        raw = raw or row.get(field)
        if status == "UNAVAILABLE":
            continue
        if status != "AVAILABLE" or not raw:
            missing.append(domain)
            continue
        if as_of:
            try:
                lhs = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                rhs = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                if lhs.tzinfo is None:
                    lhs = lhs.replace(tzinfo=UTC)
                if rhs.tzinfo is None:
                    rhs = rhs.replace(tzinfo=UTC)
                if lhs > rhs:
                    missing.append(domain)
                    future = True
            except (TypeError, ValueError):
                missing.append(domain)
    return missing, future


def _replay_provenance_summary(rows: list[dict]) -> dict[str, dict[str, str | None]]:
    """Expose a conservative domain-state summary for the replay UI."""
    summary: dict[str, dict[str, str | None]] = {}
    for domain, field in _REPLAY_DOMAINS.items():
        entries = []
        for row in rows:
            value = (row.get("provenance_domains") or {}).get(domain)
            if isinstance(value, dict) and value.get("status"):
                entries.append(value)
            elif row.get(field):
                entries.append({"status": "AVAILABLE", "as_of": row.get(field)})
            else:
                entries.append({"status": "UNKNOWN", "as_of": None})
        statuses = {str(item.get("status", "UNKNOWN")).upper() for item in entries}
        status = "UNKNOWN" if "UNKNOWN" in statuses else "AVAILABLE" if "AVAILABLE" in statuses else "UNAVAILABLE"
        as_of = next((item.get("as_of") for item in reversed(entries) if str(item.get("status", "")).upper() == "AVAILABLE"), None)
        summary[domain] = {"status": status, "as_of": str(as_of) if as_of is not None else None}
    return summary


def _reconstruct_archive_row(row: dict, horizons: tuple[str, ...]) -> tuple[dict | None, list[str], int]:
    """Rebuild a WorldState/causal shadow only from complete as-of inputs."""
    missing, _future = _replay_provenance_gaps(row, row.get("snapshot_as_of") or row.get("generated_at"))
    if missing:
        return None, missing, 0
    inputs = row.get("reconstruction_inputs")
    if not isinstance(inputs, dict):
        # A compact archive row is evidence, not a replay input.  This is the
        # critical guard against falsely labelling a row REAL_REPLAY.
        return None, ["reconstruction_inputs"], 0
    try:
        from packages.causal.engine import build_shadow
        from packages.world_state.engine import build as build_world_state
        from packages.world_state.model import WorldStateSnapshot
        generated = datetime.fromisoformat(str(row.get("snapshot_as_of") or row.get("generated_at")).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        snapshot_payload = inputs.get("market_snapshot")
        if not isinstance(snapshot_payload, dict) and row.get("snapshot_id"):
            from packages.data import snapshot_store
            stored = snapshot_store.get(str(row["snapshot_id"])) or {}
            snapshot_payload = stored.get("causal_reconstruction")
        if isinstance(snapshot_payload, dict):
            snapshot = _snapshot_from_reconstruction(row, snapshot_payload, generated)
            world = build_world_state(snapshot, now=generated)
            symbols = inputs.get("symbols") or [item.get("symbol") for item in row.get("asset_impacts") or [] if item.get("symbol")]
            shadow = build_shadow(
                world,
                symbols,
                decision_apply=False,
                technicals=inputs.get("technicals"),
                legacy_scores=inputs.get("legacy_scores"),
            )
            outcomes = list(row.get("outcomes") or [])
            return {"shadow": shadow.to_dict(), "outcomes": outcomes}, [], 1
        raw_state = inputs.get("world_state") or inputs.get("factors") or {}
        if not raw_state and row.get("snapshot_id"):
            # Reuse the canonical snapshot store when a reconstruction input
            # points at one; this keeps replay on the repository's existing
            # source of truth instead of introducing a second provider.
            from packages.data import snapshot_store
            stored = snapshot_store.get(str(row["snapshot_id"])) or {}
            raw_state = stored.get("world_state") or stored.get("factors") or {}
        if not isinstance(raw_state, dict) or not raw_state:
            return None, ["reconstruction_inputs.world_state"], 0
        allowed = {
            "liquidity", "usd_pressure", "rates_pressure", "real_yield_pressure",
            "inflation_pressure", "growth_pressure", "risk_aversion", "credit_stress",
            "energy_supply_risk", "shipping_risk", "sanctions_pressure", "trade_risk",
            "oil_pressure", "geopolitical_risk", "crypto_liquidity", "equity_risk_appetite",
            "flow_state", "regime", "global_flow_regime", "confidence", "data_quality",
        }
        state_values = {key: value for key, value in raw_state.items() if key in allowed}
        if not state_values:
            return None, ["reconstruction_inputs.world_state"], 0
        state_values.setdefault("global_flow_regime", row.get("regime") or "UNKNOWN")
        state_values.setdefault("regime", row.get("regime") or "UNKNOWN")
        state_values.setdefault("confidence", float(row.get("factor_confidence") or 0.0))
        state = WorldStateSnapshot(generated_at=generated, **state_values)
        symbols = inputs.get("symbols") or [item.get("symbol") for item in row.get("asset_impacts") or [] if item.get("symbol")]
        shadow = build_shadow(
            state,
            symbols,
            decision_apply=False,
            technicals=inputs.get("technicals"),
            legacy_scores=inputs.get("legacy_scores"),
        )
        # Outcomes are accepted solely for evaluation, after reconstruction.
        outcomes = list(row.get("outcomes") or [])
        for outcome in outcomes:
            outcome["as_of"] = row.get("snapshot_as_of")
            outcome["snapshot_as_of"] = row.get("snapshot_as_of")
        return {"shadow": shadow.to_dict(), "outcomes": outcomes}, [], 1
    except (TypeError, ValueError, KeyError):
        return None, ["reconstruction_error"], 0


def _replay_history_outcomes(row: dict, shadow: dict, horizons: tuple[str, ...]) -> list[dict]:
    """Score reconstructed predictions against stored future OHLCV only."""
    try:
        from packages.data.providers.ohlcv import history
    except Exception:
        return []
    as_of = row.get("snapshot_as_of") or row.get("generated_at")
    if not as_of:
        return []
    try:
        as_of_dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if as_of_dt.tzinfo is None:
            as_of_dt = as_of_dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return []
    steps = {"15m": ("15m", 1), "1h": ("1h", 1), "4h": ("1h", 4), "1d": ("1d", 1)}
    consensus = shadow.get("causal_consensus") or []
    impacts = {item.get("symbol"): item for item in shadow.get("impacts") or [] if item.get("symbol")}
    outputs: list[dict] = []
    for symbol, impact in impacts.items():
        try:
            causal_score = float(impact.get("direction_score"))
        except (TypeError, ValueError):
            continue
        legacy_sign = 0.0
        for item in consensus:
            if item.get("symbol") == symbol:
                direction = str(item.get("legacy_direction") or "").lower()
                legacy_sign = 1.0 if direction in {"bullish", "long", "buy"} else -1.0 if direction in {"bearish", "short", "sell"} else 0.0
                break
        for horizon in horizons:
            tf, count = steps.get(str(horizon), ("1h", 1))
            try:
                bars = history.load(str(symbol), tf)
                forward = _forward_return_pct(bars, as_of_dt, count)
            except Exception:
                forward = None
            if forward is None:
                continue
            outputs.append({
                "asset": symbol,
                "timeframe": str(horizon),
                "regime": row.get("regime", "UNKNOWN"),
                "event_type": "WORLD_STATE",
                "causal_direction": causal_score,
                "legacy_direction": legacy_sign,
                "forward_return": forward,
                "as_of": as_of,
                "snapshot_as_of": as_of,
            })
    return outputs


def _rebind_reconstructed_outcomes(outcomes: list[dict], shadow: dict) -> list[dict]:
    """Ensure materialized outcome rows use the newly rebuilt prediction."""
    directions = {
        item.get("symbol"): item.get("direction_score")
        for item in shadow.get("impacts") or ()
        if item.get("symbol")
    }
    rebound: list[dict] = []
    for original in outcomes:
        row = dict(original)
        symbol = row.get("asset") or row.get("symbol")
        if symbol in directions and directions[symbol] is not None:
            row["causal_direction"] = directions[symbol]
        rebound.append(row)
    return rebound


def causal_historical_replay(rows=None, *, min_n: int = 8, horizons: tuple[str, ...] = ("15m", "1h", "4h", "1d")) -> dict:
    """True as-of reconstruction replay, distinct from the evaluator.

    The evaluator scores already-materialised rows.  This path first proves
    domain-specific availability, reconstructs ``WorldState(T)`` and the
    existing causal graph, then passes only post-T outcomes to the evaluator.
    No archive row alone can become ``REAL_REPLAY``.
    """
    if rows is None:
        try:
            from packages.world_state.archive import all_records
            rows = all_records()
        except Exception:
            rows = []
    rows = sorted(list(rows or []), key=lambda item: str(item.get("generated_at") or item.get("snapshot_as_of") or ""))
    total = len(rows)
    if not rows:
        return {
            "status": "INSUFFICIENT_ARCHIVE", "samples": 0, "archive_coverage": 0.0,
            "archive_start": None, "archive_end": None, "timestamps_total": 0,
            "timestamps_reconstructable": 0, "timestamps_scored": 0,
            "coverage_pct": 0.0, "missing_provenance_domains": ["world_state_archive"],
            "missing_domains": ["world_state_archive"], "horizons": list(horizons),
            "by_asset": {}, "by_timeframe": {}, "by_regime": {}, "by_event_type": {},
            "future_rows_ignored": 0, "revision_leakage_blocked": 0,
            "provenance_domains": {},
            "shadow_only": True, "auto_promotion": False,
        }
    reconstructed = 0
    evaluator_rows: list[dict] = []
    missing_domains: set[str] = set()
    future_ignored = 0
    revision_blocked = 0
    for row in rows:
        as_of = row.get("snapshot_as_of") or row.get("generated_at")
        # Any future availability watermark is blocked before graph
        # reconstruction, while an explicitly UNAVAILABLE domain is accepted.
        missing, future = _replay_provenance_gaps(row, as_of)
        ingested = row.get("ingested_at")
        if ingested and as_of:
            try:
                lhs = datetime.fromisoformat(str(ingested).replace("Z", "+00:00"))
                rhs = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                if lhs.tzinfo is None:
                    lhs = lhs.replace(tzinfo=UTC)
                if rhs.tzinfo is None:
                    rhs = rhs.replace(tzinfo=UTC)
                if lhs > rhs:
                    missing.append("ingested_at")
                    future = True
            except (TypeError, ValueError):
                missing.append("ingested_at")
        if not missing:
            result, missing, count = _reconstruct_archive_row(row, horizons)
            if count:
                reconstructed += count
                outcomes = result.get("outcomes") or _replay_history_outcomes(row, result["shadow"], horizons)
                outcomes = _rebind_reconstructed_outcomes(outcomes, result["shadow"])
                evaluator_rows.extend(outcomes)
            else:
                missing_domains.update(missing)
        else:
            missing_domains.update(missing)
            future_ignored += int(future)
        if row.get("revised_value") is not None or row.get("revision"):
            revision_blocked += 1
            missing_domains.add("revisions")
    evaluator = causal_historical_evaluator(evaluator_rows, min_n=min_n)
    scored = int(evaluator.get("samples", 0) or 0)
    coverage = reconstructed / max(1, total)
    if reconstructed == 0:
        status = "INSUFFICIENT_PROVENANCE" if missing_domains else "INSUFFICIENT_ARCHIVE"
    elif scored == 0:
        status = "INSUFFICIENT_OUTCOMES"
    elif reconstructed < total:
        status = "PARTIAL_REPLAY"
    else:
        status = "REAL_REPLAY"
    if scored == 0:
        missing_domains.add("future_outcomes")
    return {
        "status": status,
        "samples": scored,
        "archive_coverage": round(coverage, 4),
        "archive_start": rows[0].get("snapshot_as_of", rows[0].get("generated_at")),
        "archive_end": rows[-1].get("snapshot_as_of", rows[-1].get("generated_at")),
        "timestamps_total": total,
        "timestamps_reconstructable": reconstructed,
        "timestamps_replayable": reconstructed,
        "timestamps_scored": scored,
        "coverage_pct": round(coverage * 100.0, 2),
        "missing_provenance_domains": sorted(missing_domains),
        "missing_domains": sorted(missing_domains),
        "provenance_domains": _replay_provenance_summary(rows),
        "horizons": list(horizons),
        "by_asset": evaluator.get("by_asset", {}),
        "by_timeframe": evaluator.get("by_timeframe", {}),
        "by_regime": evaluator.get("by_regime", {}),
        "by_event_type": evaluator.get("by_event_type", {}),
        "evaluator": evaluator,
        "future_rows_ignored": future_ignored + evaluator.get("future_rows_ignored", 0),
        "revision_leakage_blocked": revision_blocked,
        "shadow_only": True,
        "auto_promotion": False,
    }
