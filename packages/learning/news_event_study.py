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
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
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
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
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


def causal_historical_replay(rows=None, *, min_n: int = 8, horizons: tuple[str, ...] = ("15m", "1h", "4h", "1d")) -> dict:
    """Replay compact as-of World-State rows without future leakage.

    Rows are normally loaded from the canonical World-State archive.  A row is
    replayable only when it carries ``snapshot_as_of`` and the event/macro
    availability watermark.  Outcomes are scoring-only; missing future bars
    remain pending rather than being invented.
    """
    if rows is None:
        try:
            from packages.world_state.archive import all_records
            rows = all_records()
        except Exception:
            rows = []
    rows = list(rows or [])
    replay_ready = [
        row for row in rows
        if row.get("snapshot_as_of") and row.get("available_events_as_of") is not None
    ]
    evaluator_rows = []
    for row in replay_ready:
        # Archive rows may already contain materialised outcome records.  They
        # are copied only as scoring fields; all state provenance stays as-of.
        evaluator_rows.extend(row.get("outcomes") or ([row] if "forward_return" in row else []))
    evaluator = causal_historical_evaluator(evaluator_rows, min_n=min_n)
    total = len(rows)
    replayable = len(replay_ready)
    coverage = round(replayable / max(1, total), 4)
    missing_domains: list[str] = []
    if not replay_ready:
        missing_domains.extend(("world_state_archive", "available_event_watermark"))
    if replay_ready and not evaluator_rows:
        missing_domains.append("future_outcomes")
    return {
        "status": "REAL_REPLAY" if replayable else "INSUFFICIENT_ARCHIVE",
        "samples": evaluator.get("samples", 0),
        "archive_coverage": coverage,
        "archive_start": rows[0].get("snapshot_as_of", rows[0].get("generated_at")) if rows else None,
        "archive_end": rows[-1].get("snapshot_as_of", rows[-1].get("generated_at")) if rows else None,
        "timestamps_total": total,
        "timestamps_replayable": replayable,
        "coverage_pct": round(coverage * 100.0, 2),
        "missing_domains": missing_domains,
        "horizons": list(horizons),
        "evaluator": evaluator,
        "future_rows_ignored": evaluator.get("future_rows_ignored", 0),
        "shadow_only": True,
        "auto_promotion": False,
    }
