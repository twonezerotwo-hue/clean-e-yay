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
from datetime import UTC, datetime
from pathlib import Path

from packages.data.registry.loader import load_thresholds

_LEDGER_MAX_MB = 32
_HORIZON_DEFAULT = 5
_TF_DEFAULT = "1d"
_MIN_BUCKET_N_DEFAULT = 8


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
