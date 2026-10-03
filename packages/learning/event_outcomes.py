"""Olay-sonrası takip — takvim olayı açıklandıktan sonra ne oldu? SALT-GÖZLEM.

Sorun (owner, 2026-10-02 NFP): event-risk kapısı olaydan önce girişleri durduruyor,
ama olay açıklanınca sistem olayı unutuyordu — ne açıklandığı, hangi asset'lerin
etkilenmesinin beklendiği ve hangilerinin gerçekten etkilendiği hiçbir yerde
yoktu (bilgi haber akışında vardı, olaya bağlanmıyordu).

Bu modül her tick'te (ucuz, best-effort) takvim olaylarını izler:
1. Açıklanmadan önce son fiyatları taban olarak saklar.
2. Açıklamadan sonraki doğrulanmış başlıklardan sonucu çıkarır
   (zayıf/güçlü, soğuk/sıcak, güvercin/şahin) — deterministik sözlük, LLM yok.
3. Sonuca göre beklenen yönleri (config `event_outcomes.expected_low`)
   kaydeder ve 15dk / 1sa / 4sa / 1g sonra gerçekleşen hareketi ölçer.
4. Kanıt birikir: aile × sonuç × ufuk bazında "beklenen yön tuttu mu" oranı.

SALT-GÖZLEM: karar, boyut, RiskGate, event-risk kapısı DEĞİŞMEZ. Bildirim ve
panel üretir. Sistem açıklama anında kapalıysa taban/ölçüm snapshot
deposundan geriye dönük doldurulur (varsa).
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.data import snapshot_store
from packages.data.providers import calendar as calendar_provider
from packages.data.providers.news import classify
from packages.data.registry.loader import load_thresholds
from packages.notifications import Notification, make_id
from packages.ops.store import write_text_atomic

SCHEMA_VERSION = 1
_MAX_RECORDS = 120
_DEADBAND_PCT = 0.02  # bu kadar küçük hareket "yatay" sayılır (yön isabetine girmez)
_LIVE_CAPTURE_TOLERANCE_S = 300  # ufuk anından sonra bu kadar içinde canlı fiyat geçerli
_STORE_GAP_S = 900  # snapshot deposunda kabul edilen en büyük zaman farkı

_DEFAULT_HORIZONS = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
# ABD makro sürprizinin varsayılan fiyatlanması: faiz kanalı (Fed beklentisi).
# low = zayıf istihdam / düşük enflasyon / güvercin Fed; high = tersi (negatifi).
_DEFAULT_EXPECTED_LOW = {
    "DXY": -1, "US10Y": -1, "XAUUSD": 1, "XAGUSD": 1, "BTCUSD": 1,
    "ETHUSD": 1, "SP500": 1, "NVDA": 1, "VIX": -1,
}

_FAMILY_WORDS: dict[str, tuple[str, ...]] = {
    "jobs": ("payroll", "nonfarm", "non-farm", "jobs report", "jobs data", "job growth",
             "jobs", "unemployment rate", "labor market", "hiring", "istihdam"),
    "inflation": ("cpi", "consumer price", "inflation", "ppi", "producer price", "pce",
                  "enflasyon", "tüfe"),
    "central_bank": ("fomc", "federal reserve", "fed ", "fed's", "powell", "rate decision",
                     "minutes"),
}
_US_MARKERS = ("u.s.", "us ", "u.s ", "american", "wall st", "treasury", "fed", "nasdaq",
               "s&p", "dow", "abd")
_FOREIGN_MARKERS = ("eurozone", "euro zone", "euro area", "ecb", "britain", "british", "uk ",
                    "bank of england", "china", "chinese", "japan", "boj", "germany", "german",
                    "canada", "australia", "rba", "india", "turkey", "türkiye", "iran", "swiss",
                    "korea", "brazil", "mexico")
_PREVIEW_WORDS = ("ahead of", "await", "preview", "what to expect", "before the", "expected to show")

# Sürpriz yönü sözlüğü tek kaynak: news/classify (haber yönü de aynısını kullanır).
_LOW_RE = classify.MACRO_LOW_RE
_HIGH_RE = classify.MACRO_HIGH_RE

_OUTCOME_LABEL = {
    ("jobs", "low"): "ZAYIF (beklenti altı)",
    ("jobs", "high"): "GÜÇLÜ (beklenti üstü)",
    ("inflation", "low"): "DÜŞÜK / soğuk",
    ("inflation", "high"): "YÜKSEK / sıcak",
    ("central_bank", "low"): "GÜVERCİN",
    ("central_bank", "high"): "ŞAHİN",
}


def _path() -> Path:
    return Path(os.environ.get("EVENT_OUTCOMES_PATH", "data/runtime/event_outcomes.json"))


def _cfg() -> dict[str, Any]:
    try:
        raw = load_thresholds().get("event_outcomes") or {}
    except (OSError, KeyError, ValueError, TypeError):
        raw = {}
    horizons = raw.get("horizons_min") or _DEFAULT_HORIZONS
    expected = raw.get("expected_low") or _DEFAULT_EXPECTED_LOW
    return {
        "baseline_lead_min": float(raw.get("baseline_lead_min", 30)),
        "headline_window_min": float(raw.get("headline_window_min", 180)),
        "horizons": {str(k): int(v) for k, v in dict(horizons).items()},
        "expected_low": {str(k): (1 if float(v) > 0 else -1) for k, v in dict(expected).items()},
        "min_votes": int(raw.get("min_votes", 2)),
        "min_share": float(raw.get("min_share", 0.7)),
    }


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    try:
        out = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def family_of(event: Mapping[str, Any]) -> str:
    text = f"{event.get('id', '')} {event.get('title', '')}".lower()
    if any(k in text for k in ("nfp", "istihdam", "payroll", "jobs")):
        return "jobs"
    if any(k in text for k in ("cpi", "ppi", "pce", "enflasyon", "inflation")):
        return "inflation"
    if any(k in text for k in ("fomc", "fed", "faiz")):
        return "central_bank"
    return "other"


def _headline_fields(h: Any) -> tuple[str, datetime | None, str, bool]:
    if isinstance(h, Mapping):
        return (str(h.get("title") or ""), _parse(h.get("ts")), str(h.get("source") or ""),
                bool(h.get("verified", True)))
    return (str(getattr(h, "title", "") or ""), _parse(getattr(h, "ts", None)),
            str(getattr(h, "source", "") or ""), bool(getattr(h, "verified", True)))


def classify_headline(title: str, family: str) -> str | None:
    """Başlık bu olay ailesine aitse sürpriz oyu: "low" / "high" / "none"; değilse None."""
    t = f" {title.lower()} "
    words = _FAMILY_WORDS.get(family)
    if not words or not any(w in t for w in words):
        return None
    if any(w in t for w in _PREVIEW_WORDS):
        return None
    if any(w in t for w in _FOREIGN_MARKERS) and not any(w in t for w in _US_MARKERS):
        return None
    low = bool(_LOW_RE.search(t))
    high = bool(_HIGH_RE.search(t))
    if low and not high:
        return "low"
    if high and not low:
        return "high"
    return "none"


def _outcome(record: dict, headlines: Iterable[Any], cfg: dict, now: datetime) -> None:
    """Başlıklardan sonucu güncelle (açıklamadan sonra, pencere içinde; birikimli)."""
    release = _parse(record["release_ts"])
    if release is None or now < release:
        return
    window_end = release + timedelta(minutes=cfg["headline_window_min"])
    oc = record.setdefault("outcome", {"direction": "unknown", "votes": {"low": 0, "high": 0, "none": 0},
                                       "headlines": [], "label": "henüz sonuç başlığı yok"})
    seen = {h["title"] for h in oc["headlines"]}
    for h in headlines or ():
        title, ts, source, verified = _headline_fields(h)
        if not verified or not title or title in seen or ts is None:
            continue
        if not (release <= ts <= window_end):
            continue
        vote = classify_headline(title, record["family"])
        if vote is None:
            continue
        seen.add(title)
        oc["votes"][vote] = oc["votes"].get(vote, 0) + 1
        if len(oc["headlines"]) < 40:
            oc["headlines"].append({"ts": _iso(ts), "title": title[:200], "source": source, "vote": vote})
    low, high = oc["votes"].get("low", 0), oc["votes"].get("high", 0)
    n = low + high
    if n == 0:
        direction = "unknown"
    else:
        top, top_dir = (low, "low") if low >= high else (high, "high")
        direction = top_dir if (top >= cfg["min_votes"] and top / n >= cfg["min_share"]) else "mixed"
    if direction != oc["direction"] and direction in {"low", "high"} and not oc.get("decided_at"):
        oc["decided_at"] = _iso(now)
    oc["direction"] = direction
    if direction in {"low", "high"}:
        oc["label"] = _OUTCOME_LABEL.get((record["family"], direction),
                                         "BEKLENTİ ALTI" if direction == "low" else "BEKLENTİ ÜSTÜ")
    elif direction == "mixed":
        oc["label"] = "KARIŞIK (başlıklar çelişiyor)"
    if direction in {"low", "high"} and record["family"] != "other":
        sign = 1 if direction == "low" else -1
        record["expected"] = {s: d * sign for s, d in cfg["expected_low"].items()}
    else:
        record["expected"] = {}


def _prices_from_doc(doc: dict | None) -> dict[str, float]:
    if not doc:
        return {}
    rows = (doc.get("data_snapshot") or {}).get("prices") or []
    out: dict[str, float] = {}
    for q in rows:
        try:
            px = float(q.get("price"))
        except (TypeError, ValueError, AttributeError):
            continue
        if px > 0:
            out[str(q.get("symbol"))] = px
    return out


def _moves(base: Mapping[str, float], cur: Mapping[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym, b in base.items():
        c = cur.get(sym)
        if b and c:
            out[sym] = round((float(c) / float(b) - 1.0) * 100.0, 3)
    return out


def _hits(expected: Mapping[str, int], moves: Mapping[str, float]) -> dict[str, Any]:
    per: dict[str, str] = {}
    for sym, d in expected.items():
        mv = moves.get(sym)
        if mv is None:
            continue
        if abs(mv) < _DEADBAND_PCT:
            per[sym] = "flat"
        else:
            per[sym] = "hit" if (mv > 0) == (d > 0) else "miss"
    hit = sum(1 for v in per.values() if v == "hit")
    scored = sum(1 for v in per.values() if v != "flat")
    return {"per_asset": per, "hit": hit, "scored": scored}


def _measure(record: dict, prices: Mapping[str, float], cfg: dict, now: datetime) -> list[str]:
    """Taban + ufuk ölçümleri. Dönen liste: bu çağrıda tamamlanan ufuklar."""
    release = _parse(record["release_ts"])
    if release is None:
        return []
    lead = timedelta(minutes=cfg["baseline_lead_min"])
    base = record.setdefault("baseline", {"ts": None, "prices": {}, "source": None})
    if release - lead <= now < release and prices:
        base.update(ts=_iso(now), prices={k: float(v) for k, v in prices.items() if v}, source="tick")
    if now >= release and not base["prices"] and not base.get("store_tried"):
        base["store_tried"] = True
        doc = snapshot_store.nearest(release, side="before", max_gap_seconds=_STORE_GAP_S)
        px = _prices_from_doc(doc)
        if px:
            base.update(ts=(doc or {}).get("generated_at"), prices=px, source="snapshot_store")
    done: list[str] = []
    realized = record.setdefault("realized", {})
    for name, minutes in cfg["horizons"].items():
        if name in realized:
            continue
        due = release + timedelta(minutes=minutes)
        if now < due:
            continue
        cur: dict[str, float] = {}
        src = None
        if prices and (now - due).total_seconds() <= _LIVE_CAPTURE_TOLERANCE_S:
            cur, src, at = {k: float(v) for k, v in prices.items() if v}, "tick", _iso(now)
        else:
            doc = snapshot_store.nearest(due, side="after", max_gap_seconds=_STORE_GAP_S)
            cur, src, at = _prices_from_doc(doc), "snapshot_store", (doc or {}).get("generated_at")
        if not base["prices"] or not cur:
            realized[name] = {"ts": None, "source": None, "moves": {}, "missing": True}
            continue
        realized[name] = {"ts": at, "source": src, "moves": _moves(base["prices"], cur), "missing": False}
        done.append(name)
    return done


def _status(record: dict, cfg: dict, now: datetime) -> str:
    release = _parse(record["release_ts"])
    if release is None or now < release:
        return "UPCOMING"
    longest = max(cfg["horizons"].values() or [0])
    if len(record.get("realized") or {}) >= len(cfg["horizons"]) or now > release + timedelta(minutes=longest + 60):
        return "DONE"
    if (record.get("outcome") or {}).get("direction") in {None, "unknown"}:
        return "AWAITING_RESULT"
    return "MEASURING"


def _load() -> dict:
    p = _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("events"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "events": {}}


def _save(state: dict, now: datetime) -> None:
    events = state["events"]
    if len(events) > _MAX_RECORDS:
        keep = sorted(events.values(), key=lambda r: r["release_ts"])[-_MAX_RECORDS:]
        state["events"] = {r["id"]: r for r in keep}
    state["updated_at"] = _iso(now)
    state["schema_version"] = SCHEMA_VERSION
    write_text_atomic(_path(), json.dumps(state, ensure_ascii=False, indent=1, default=str))


def _fmt_moves(record: dict, horizon: str) -> str:
    r = (record.get("realized") or {}).get(horizon) or {}
    moves, expected = r.get("moves") or {}, record.get("expected") or {}
    syms = [s for s in expected if s in moves] or sorted(moves, key=lambda s: -abs(moves[s]))[:5]
    parts = []
    for s in syms[:6]:
        mark = ""
        if s in expected and abs(moves[s]) >= _DEADBAND_PCT:
            mark = " ✓" if (moves[s] > 0) == (expected[s] > 0) else " ✗"
        parts.append(f"{s} {moves[s]:+.2f}%{mark}")
    return ", ".join(parts)


def _notifications(record: dict, newly_done: list[str], decided_now: bool, now: datetime) -> list[Notification]:
    out: list[Notification] = []
    priority = "high" if record.get("importance") in {"high", "critical"} else "medium"
    title = record.get("title") or record["id"]
    oc = record.get("outcome") or {}
    if decided_now:
        exp = record.get("expected") or {}
        exp_txt = ", ".join(f"{s}{'↑' if d > 0 else '↓'}" for s, d in list(exp.items())[:6]) or "—"
        n = oc.get("votes", {}).get(oc.get("direction"), 0)
        out.append(Notification(
            id=make_id("event_outcome"), ts=_iso(now), type="event_outcome", priority=priority,
            title=f"Açıklandı: {title} → {oc.get('label')}",
            body_short=f"{n} doğrulanmış başlık · beklenen: {exp_txt}",
            body_long=(f"{title} açıklandı. Başlıklara göre sonuç: {oc.get('label')} ({n} başlık). "
                       f"Faiz kanalı varsayımıyla beklenen yön: {exp_txt}. Gerçekleşen tepki "
                       "15dk / 1sa / 4sa / 1g sonra ölçülecek. Karar zinciri değişmez (salt-gözlem)."),
        ))
    one_h = (record.get("realized") or {}).get("1h") or {}
    if "1h" in newly_done and one_h.get("source") == "tick":
        h = _hits(record.get("expected") or {}, one_h.get("moves") or {})
        score = f"{h.get('hit', 0)}/{h.get('scored', 0)} beklenen yönde" if h.get("scored") else "beklenti yok"
        out.append(Notification(
            id=make_id("event_reaction"), ts=_iso(now), type="event_outcome", priority="medium",
            title=f"Tepki (1 saat): {title}",
            body_short=f"{_fmt_moves(record, '1h')} · {score}",
            body_long=(f"{title} açıklamasından 1 saat sonra: {_fmt_moves(record, '1h')}. "
                       f"Sonuç: {oc.get('label', '—')}; {score}."),
        ))
    return out


_BACKFILL_OFFSETS_MIN = (10, 20, 30, 45, 60, 90, 120, 180)


def _store_headlines(release: datetime, now: datetime) -> list[dict]:
    """Sistem açıklamada kapalıysa: deposundan birkaç örnek snapshot'ın başlıkları."""
    out: list[dict] = []
    for m in _BACKFILL_OFFSETS_MIN:
        at = release + timedelta(minutes=m)
        if at > now:
            break
        doc = snapshot_store.nearest(at, side="after", max_gap_seconds=_STORE_GAP_S)
        out.extend((doc or {}).get("causal_reconstruction", {}).get("headlines") or [])
    return out


def track(
    *,
    prices: Mapping[str, float],
    headlines: Iterable[Any] | None,
    now: datetime | None = None,
    calendar_path: Path | None = None,
) -> list[Notification]:
    """Tick başına çağrılır: takvim olaylarını izler, kaydı günceller, bildirim döner."""
    cfg = _cfg()
    now = now or datetime.now(UTC)
    longest = max(cfg["horizons"].values() or [60]) / 60.0
    window = calendar_provider.events_in_window(
        now, past_hours=longest + 2.0, future_hours=cfg["baseline_lead_min"] / 60.0 + 0.5,
        yaml_path=calendar_path,
    )
    if not window:
        return []
    state = _load()
    headlines = list(headlines or ())
    notifs: list[Notification] = []
    for ev in window:
        rec = state["events"].get(ev["id"])
        if rec is None:
            rec = {
                "id": ev["id"], "title": ev["title"], "category": ev.get("category"),
                "importance": ev.get("importance"), "market_impact": ev.get("market_impact"),
                "release_ts": _iso(ev["release_ts"]), "time_source": ev.get("time_source"),
                "family": family_of(ev),
            }
            state["events"][ev["id"]] = rec
        release = _parse(rec["release_ts"])
        decided_now = False
        if release is not None and now >= release:
            in_window = now <= release + timedelta(minutes=cfg["headline_window_min"])
            before = (rec.get("outcome") or {}).get("decided_at")
            if in_window:
                _outcome(rec, headlines, cfg, now)
            undecided = (rec.get("outcome") or {}).get("direction") in {None, "unknown"}
            if undecided and not rec.get("headline_backfill") and now - release >= timedelta(minutes=10):
                rec["headline_backfill"] = True  # bir kez: depo örnekleri (sistem kapalıyken kaçanlar)
                _outcome(rec, _store_headlines(release, now), cfg, now)
            # Geç (pencere dışı) doldurulan sonuç için bildirim yok — bayat haber olur.
            decided_now = in_window and before is None and bool((rec.get("outcome") or {}).get("decided_at"))
        newly_done = _measure(rec, prices, cfg, now)
        rec["status"] = _status(rec, cfg, now)
        rec["checked_at"] = _iso(now)
        notifs += _notifications(rec, newly_done, decided_now, now)
    _save(state, now)
    return notifs


def summary(records: Iterable[dict]) -> dict[str, Any]:
    """Aile × sonuç × ufuk: beklenen yön ne sıklıkla tuttu (kanıt birikimi)."""
    buckets: dict[str, dict[str, Any]] = {}
    for rec in records:
        direction = (rec.get("outcome") or {}).get("direction")
        if direction not in {"low", "high"}:
            continue
        key = f"{rec.get('family')}:{direction}"
        b = buckets.setdefault(key, {"family": rec.get("family"), "direction": direction,
                                     "events": 0, "horizons": {}})
        b["events"] += 1
        for name, r in (rec.get("realized") or {}).items():
            h = _hits(rec.get("expected") or {}, r.get("moves") or {})
            if not h.get("scored"):
                continue
            hz = b["horizons"].setdefault(name, {"hit": 0, "scored": 0})
            hz["hit"] += h["hit"]
            hz["scored"] += h["scored"]
    for b in buckets.values():
        for hz in b["horizons"].values():
            hz["hit_rate"] = round(hz["hit"] / hz["scored"], 3) if hz["scored"] else None
    return {"buckets": sorted(buckets.values(), key=lambda b: (b["family"], b["direction"])),
            "note": "Az olayla oran gürültülüdür; karar zincirine bağlanmaz (owner kararı gerekir)."}


def viewmodel(now: datetime | None = None, calendar_path: Path | None = None) -> dict[str, Any]:
    """API/panel: yaklaşan olaylar (kesin saat) + son açıklananlar + kanıt özeti."""
    cfg = _cfg()
    now = now or datetime.now(UTC)
    state = _load()
    records = sorted(state["events"].values(), key=lambda r: r["release_ts"], reverse=True)
    upcoming = [
        {"id": e["id"], "title": e["title"], "importance": e.get("importance"),
         "release_ts": _iso(e["release_ts"]), "time_source": e.get("time_source"),
         "minutes_until": round((e["release_ts"] - now).total_seconds() / 60.0, 1)}
        for e in calendar_provider.events_in_window(now, past_hours=0, future_hours=7 * 24,
                                                    yaml_path=calendar_path)[:5]
    ]
    recent = []
    for r in records[:12]:
        oc = r.get("outcome") or {}
        recent.append({
            "id": r["id"], "title": r.get("title"), "family": r.get("family"),
            "importance": r.get("importance"), "release_ts": r["release_ts"],
            "time_source": r.get("time_source"), "status": _status(r, cfg, now),
            "market_impact": r.get("market_impact"),
            "outcome": {"direction": oc.get("direction", "unknown"), "label": oc.get("label"),
                        "votes": oc.get("votes") or {}, "decided_at": oc.get("decided_at"),
                        "headlines": (oc.get("headlines") or [])[:6]},
            "expected": r.get("expected") or {},
            "baseline_source": (r.get("baseline") or {}).get("source"),
            "realized": {k: {"ts": v.get("ts"), "source": v.get("source"), "missing": v.get("missing", False),
                             "moves": v.get("moves") or {},
                             "hits": _hits(r.get("expected") or {}, v.get("moves") or {})}
                         for k, v in (r.get("realized") or {}).items()},
        })
    return {
        "generated_at": _iso(now),
        "mode": "observe_only",
        "horizons": list(cfg["horizons"]),
        "upcoming": upcoming,
        "recent": recent,
        "summary": summary(state["events"].values()),
        "assumption": {"expected_low": cfg["expected_low"],
                       "note": "Faiz kanalı varsayımı: zayıf veri / düşük enflasyon / güvercin Fed → "
                               "dolar ve faiz ↓, altın-kripto-hisse ↑. 'high' sonuçta tersi."},
    }


def compact_for_chat(now: datetime | None = None, *, hours: float = 48.0) -> dict[str, Any]:
    """Sohbet bağlamı: son açıklananların kısa özeti + sıradaki olay (kesin saat)."""
    now = now or datetime.now(UTC)
    vm = viewmodel(now)
    recent = []
    for r in vm["recent"]:
        rel = _parse(r["release_ts"])
        if r["status"] == "UPCOMING" or rel is None or now - rel > timedelta(hours=hours):
            continue
        exp = r["expected"]
        recent.append({
            "title": r["title"], "released_at": r["release_ts"], "status": r["status"],
            "outcome": r["outcome"]["label"], "headline_votes": r["outcome"]["votes"],
            "expected": {s: ("up" if d > 0 else "down") for s, d in exp.items()},
            "reaction": {h: {"moves_pct": {s: v["moves"][s] for s in (list(exp) or list(v["moves"])[:6])
                                           if s in v["moves"]},
                             "in_expected_direction": f"{(v['hits'] or {}).get('hit', 0)}/{(v['hits'] or {}).get('scored', 0)}"}
                         for h, v in r["realized"].items() if not v.get("missing")},
        })
    nxt = next((u for u in vm["upcoming"] if u["minutes_until"] >= 0), None)
    return {"recent_releases": recent[:2],
            "next_event": ({"title": nxt["title"], "release_at": nxt["release_ts"]} if nxt else None)}


__all__ = ["classify_headline", "compact_for_chat", "family_of", "summary", "track", "viewmodel"]
