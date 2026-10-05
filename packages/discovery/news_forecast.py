"""Haber öngörüsü (owner kararı 2026-10-05) — keşif + işlem evreni. SALT-GÖZLEM.

Soru: haber akışına göre hangi varlığın fiyatı yukarı / aşağı gidecek gibi görünüyor?
Her learning turunda (ucuz, ağ yalnız sınırlı web aramasında):

1. Başlık defteri: son snapshot'ların doğrulanmış RSS başlıkları + en güçlü keşif
   adayları için sınırlı web araması (Tavily; aday başına `min_interval_hours`'da
   bir) → `window_hours` kayan pencere, başlığa göre dedupe.
2. Eşleme: işlem evreni varlıkları ingest anında hesaplanmış `asset_impact` (E2
   kurallı) ile; keşif adayları ad / cg_id / sembol (büyük harf), emtia ve sektörler
   config anahtar kelimeleriyle — KELİME SINIRIYLA (alt-dize hatası yok).
3. Yön: başlığın açıkça söylediği hareket (`classify.stated_move`), yoksa duygu.
4. Ağırlık: kaynak güvenilirliği (`news_event_study` kova isabeti) × tazelik.
5. Öngörü: varlık başına yön (up/down/neutral), güç 0–100, kanıt başlıkları.
6. Öngörü karnesi: güçlü yönlü öngörüler fiyatıyla açılır, +4sa/+1g/+3g'de çözülür
   (ayrı JSONL defter) → isabet oranı. Öngörünün gerçekten işe yarayıp yaramadığı ölçülür.

Karar, boyut, RiskGate, evren değişmez; yalnız fikir panosu ve karne beslenir.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.data import snapshot_store
from packages.data.providers.news import classify
from packages.data.registry import assets as asset_registry
from packages.ops.store import write_text_atomic

SCHEMA_VERSION = 1
_MAX_HEADLINES = 1500
_MAX_OPEN = 300
_DIRECTION_EPS = 0.15
_FLAT_PCT = 0.1
# Gündelik İngilizce kelimeyle çakışan kripto sembolleri büyük harf eşleşmesinde
# bile sayılmaz ("NEAR record high" ≠ NEAR Protocol). Ad eşleşmesi yine çalışır.
_STOP_TICKERS = frozenset({
    "NEAR", "ONE", "ALL", "ANY", "FUN", "GAS", "KEY", "NOW", "TOP", "BIG", "NEW", "OPEN",
    "SUN", "CAT", "DOG", "PUMP", "LAB", "HYPE", "RAIN", "MOVE", "AI", "IT", "US", "UK",
})
_LLM_CONF_W = {"low": 0.6, "med": 0.9, "high": 1.2}  # YZ güveni → başlık ağırlığı çarpanı
_STOP_NAMES = frozenset({"near", "pump", "hype", "rain", "move", "open", "one"})


def _state_path() -> Path:
    return Path(os.environ.get("NEWS_FORECAST_PATH", "data/runtime/news_forecast.json"))


def _ledger_path() -> Path:
    return Path(os.environ.get("NEWS_FORECAST_LEDGER_PATH", "data/runtime/news_forecast_ledger.jsonl"))


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if not ts:
        return None
    raw = str(ts).strip()
    for parse in (lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
                  lambda s: datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %Z")):
        try:
            out = parse(raw)
            return out if out.tzinfo else out.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


def config(discovery_cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if discovery_cfg is None:
        from packages.discovery import scanner

        discovery_cfg = scanner.load_config()
    raw = dict((discovery_cfg or {}).get("news_forecast") or {})
    web = dict(raw.get("web_search") or {})
    return {
        "window_hours": float(raw.get("window_hours", 72)),
        "half_life_hours": max(1.0, float(raw.get("half_life_hours", 24))),
        "snapshots_per_run": int(raw.get("snapshots_per_run", 12)),
        "min_track_strength": float(raw.get("min_track_strength", 25)),
        "resolve_hours": [int(h) for h in (raw.get("resolve_hours") or [4, 24, 72])],
        "web_max_assets": int(web.get("max_assets_per_run", 5)),
        "web_interval_hours": float(web.get("min_interval_hours", 6)),
        "web_max_results": int(web.get("max_results", 5)),
        "sector_keywords": {str(k): [str(t) for t in v] for k, v in dict(raw.get("sector_keywords") or {}).items()},
    }


# ---------------------------------------------------------------------------
# Varlık listesi + eşleme terimleri
# ---------------------------------------------------------------------------

def _asset(symbol: str, kind: str, name: str, ci_terms: Iterable[str] = (), cs_terms: Iterable[str] = ()) -> dict:
    return {
        "symbol": symbol, "kind": kind, "name": name,
        "ci_terms": sorted({t.lower() for t in ci_terms if t and len(t) >= 3}),
        "cs_terms": sorted({t for t in cs_terms if t and len(t) >= 3 and t not in _STOP_TICKERS}),
    }


def build_assets(scan_artifact: Mapping[str, Any], discovery_cfg: Mapping[str, Any], cfg: Mapping[str, Any],
                 news_candidates: list[dict] | None = None) -> dict[str, dict]:
    """İşlem evreni + keşif evreni (kripto kısa listesi, tüm emtia, sektörler)."""
    out: dict[str, dict] = {}
    for a in asset_registry.all_assets():
        out[a.symbol] = _asset(a.symbol, "universe", str(getattr(a, "label", "") or a.symbol))
        out[a.symbol]["registry"] = True
    for c in (scan_artifact.get("crypto_universe") or {}).get("candidates") or []:
        sym = str(c.get("symbol") or "")
        if not sym or sym in out:
            continue
        name = str(c.get("name") or "")
        base = sym[:-3] if sym.endswith("USD") else sym
        ci = [name] if name.lower() not in _STOP_NAMES else []
        cg = str(c.get("cg_id") or "").replace("-", " ")
        if cg and cg not in _STOP_NAMES and cg != name.lower():
            ci.append(cg)
        out[sym] = _asset(sym, "crypto", name or base, ci, [base])
    for sym, meta in dict((discovery_cfg.get("commodities") or {}).get("items") or {}).items():
        meta = dict(meta or {})
        out[str(sym)] = _asset(str(sym), "commodity", str(meta.get("label") or sym), meta.get("keywords") or [])
    sectors = dict((discovery_cfg.get("sector_rotation") or {}).get("sectors") or {})
    for sym, terms in dict(cfg.get("sector_keywords") or {}).items():
        label = str(dict(sectors.get(sym) or {}).get("label") or sym)
        out[sym] = _asset(sym, "sector_etf", label, terms, [sym])
    # Haber güdümlü keşif adayları (2026-10-05, ikinci tur): YZ'nin bulduğu, doğrulanmış varlıklar.
    for c in news_candidates if news_candidates is not None else _news_candidates():
        sym = str(c.get("symbol") or "")
        if not sym or sym in out:
            continue
        name = str(c.get("name") or sym)
        base = re.split(r"[=\-.^]", str(c.get("ticker") or sym))[0]
        out[sym] = _asset(sym, "news", name, [name] if name.lower() not in _STOP_NAMES else [], [base])
    return out


def _news_candidates() -> list[dict]:
    try:
        from packages.discovery import news_discovery

        return news_discovery.all_candidates()
    except Exception:  # keşif defteri okunamazsa öngörü yine koşar
        return []


def _matches(asset: Mapping[str, Any], title: str) -> list[str]:
    """Başlıkta geçen terimler (kelime sınırıyla; semboller büyük harf)."""
    lower = title.lower()
    hits = [t for t in asset["ci_terms"] if re.search(r"(?<![\w$])" + re.escape(t) + r"(?![\w])", lower)]
    hits += [t for t in asset["cs_terms"] if re.search(r"(?<![A-Za-z0-9])\$?" + re.escape(t) + r"(?![A-Za-z0-9])", title)]
    return hits


# ---------------------------------------------------------------------------
# Başlık defteri
# ---------------------------------------------------------------------------

def _key(title: str) -> str:
    return hashlib.sha1(re.sub(r"\W+", " ", title.lower()).strip().encode("utf-8")).hexdigest()[:16]


def _ingest_snapshot_headlines(store: dict[str, dict], docs: Iterable[Mapping[str, Any]], now: datetime) -> int:
    added = 0
    for doc in docs:
        for h in (doc.get("causal_reconstruction") or {}).get("headlines") or []:
            title = str(h.get("title") or "").strip()
            if not title or not h.get("verified", False):
                continue
            k = _key(title)
            if k in store:
                continue
            store[k] = {
                "title": title[:240], "source": str(h.get("source") or ""), "origin": "rss",
                "ts": _iso(_parse(h.get("ts")) or now), "sentiment": h.get("sentiment") or "neutral",
                "impact": dict(h.get("asset_impact") or {}), "url": h.get("url"),
            }
            added += 1
    return added


def _ingest_web(store: dict[str, dict], asset: Mapping[str, Any], hits: Iterable[Any], now: datetime) -> int:
    added = 0
    for hit in hits:
        title = str(getattr(hit, "title", "") or "").strip()
        content = str(getattr(hit, "content", "") or "")
        if not title or not (_matches(asset, title) or _matches(asset, content)):
            continue  # ilgisiz arama sonucu sayılmaz
        k = _key(title)
        if k in store:
            continue
        url = str(getattr(hit, "url", "") or "")
        source = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", url) or ["web"])[0])
        store[k] = {
            "title": title[:240], "source": source, "origin": "web",
            "ts": _iso(_parse(getattr(hit, "published_date", None)) or now),
            "sentiment": classify.classify_sentiment_active(f"{title}. {content}"),
            "impact": {}, "url": url, "asset_hint": asset["symbol"],
        }
        added += 1
    return added


def _reclassify(store: dict[str, dict]) -> int:
    """Kayıtlı varlık etkisini GÜNCEL sınıflandırıcıyla yeniden hesaplar. Sınıflandırıcı
    düzeltmeleri 72 saatlik defterde geriye dönük geçerli olsun diye (2026-10-05: alt-dize →
    kelime sınırı düzeltmesinden önce gelen "September" başlıkları TEM'e yazılı kalmıştı)."""
    changed = 0
    for h in store.values():
        if h.get("origin") != "rss":
            continue
        new = classify.classify_asset_impact(h["title"], h.get("sentiment") or "neutral")
        if new != dict(h.get("impact") or {}):
            h["impact"] = new
            changed += 1
    return changed


def _ingest_llm(store: dict[str, dict], rows: Iterable[Mapping[str, Any]], now: datetime) -> int:
    """Haber keşfinin YZ çıkarımı: başlığın hangi varlığı hangi yönde etkileyeceği.
    Aynı başlık defterde varsa etki ona eklenir; yoksa (ham akıştan) yeni kayıt açılır."""
    added = 0
    for row in rows:
        title = str(row.get("title") or "").strip()
        if not title or not row.get("impacts"):
            continue
        k = _key(title)
        if k not in store:
            store[k] = {"title": title[:240], "source": str(row.get("source") or ""), "origin": "rss",
                        "ts": _iso(_parse(row.get("ts")) or now), "sentiment": "neutral", "impact": {}}
            added += 1
        store[k]["llm_impacts"] = dict(row["impacts"])
        store[k]["consequence"] = row.get("consequence")
    return added


def _web_query(asset: Mapping[str, Any]) -> str:
    if asset["kind"] == "crypto":
        return f"{asset['name']} crypto price news"
    first = (asset["ci_terms"] or [asset["name"]])[0]
    return f"{first} price news" if asset["kind"] == "commodity" else f"{first} news"


# ---------------------------------------------------------------------------
# Ağırlık + öngörü
# ---------------------------------------------------------------------------

def _load_source_table() -> dict:
    try:
        from packages.learning import news_event_study

        return news_event_study._load_table() or {}
    except Exception:
        return {}


def source_weight(table: Mapping[str, Any], source: str, sentiment: str, origin: str) -> float:
    """Kaynak güvenilirliği: öngörücü kova ağır, kanıtsız nötr, web hafif."""
    if origin == "web":
        return 0.7
    bucket = (table.get("buckets") or {}).get(f"{source}|{sentiment}") or {}
    verdict = bucket.get("verdict")
    if verdict == "PREDICTIVE":
        hit = float(bucket.get("hit_rate") or 0.5)
        return round(min(1.6, max(1.0, 1.0 + (hit - 0.5) * 2.0)), 3)
    if verdict == "NO_EDGE":
        return 0.8
    return 1.0


def _headline_direction(asset: Mapping[str, Any], h: Mapping[str, Any], terms: list[str]) -> float | None:
    """Başlığın bu varlık için yönü; ilgisizse None."""
    llm = (h.get("llm_impacts") or {}).get(asset["symbol"])
    if llm is not None:  # YZ sonuç zinciri bu varlığı açıkça bağladı → önce o
        return float(llm["d"])
    if asset.get("registry"):
        impact = h.get("impact") or {}
        if asset["symbol"] not in impact:
            return None
        return float(impact[asset["symbol"]])
    if h.get("asset_hint") and h["asset_hint"] != asset["symbol"]:
        return None
    if not terms:
        return None
    stated = classify.stated_move(h["title"], terms)
    return stated if stated is not None else classify.direction_of(h.get("sentiment"))


def forecast_for(asset: Mapping[str, Any], headlines: Iterable[Mapping[str, Any]], table: Mapping[str, Any],
                 now: datetime, half_life_hours: float) -> dict | None:
    contribs: list[tuple[float, float, Mapping[str, Any]]] = []
    for h in headlines:
        terms = _matches(asset, h["title"]) if not asset.get("registry") else []
        d = _headline_direction(asset, h, terms)
        if d is None:
            continue
        age_h = max(0.0, (now - (_parse(h.get("ts")) or now)).total_seconds() / 3600.0)
        w = source_weight(table, h.get("source", ""), h.get("sentiment") or "neutral", h.get("origin", "rss"))
        w *= math.exp(-math.log(2) * age_h / half_life_hours)
        llm = (h.get("llm_impacts") or {}).get(asset["symbol"])
        if llm is not None:
            w *= _LLM_CONF_W.get(str(llm.get("k") or "med"), 0.9)
        contribs.append((d, w, h))
    if not contribs:
        return None
    wsum = sum(w for _, w, _ in contribs)
    if wsum <= 0:
        return None
    score = sum(d * w for d, w, _ in contribs) / wsum
    confidence = min(1.0, wsum / 3.0)  # ~3 taze güvenilir başlık = tam güven
    direction = "up" if score >= _DIRECTION_EPS else "down" if score <= -_DIRECTION_EPS else "neutral"
    top = sorted(contribs, key=lambda c: -c[1])[:3]
    return {
        "symbol": asset["symbol"], "kind": asset["kind"], "name": asset["name"],
        "direction": direction,
        "strength": round(abs(score) * confidence * 100),
        "score": round(score, 3),
        "n_headlines": len(contribs),
        "weight_sum": round(wsum, 3),
        "evidence": [{"title": h["title"], "source": h.get("source"), "ts": h.get("ts"),
                      "direction": d, "origin": "llm" if asset["symbol"] in (h.get("llm_impacts") or {})
                      else h.get("origin"), "url": h.get("url")} for d, _, h in top],
    }


# ---------------------------------------------------------------------------
# Öngörü karnesi (fiyatla çözülür)
# ---------------------------------------------------------------------------

def current_prices(scan_artifact: Mapping[str, Any], latest_snapshot: Mapping[str, Any] | None, now: datetime) -> dict[str, float]:
    """İşlem evreni: son snapshot; keşif: tarama sonucunun son kapanışı (≤3 saatlik)."""
    out: dict[str, float] = {}
    for q in ((latest_snapshot or {}).get("data_snapshot") or {}).get("prices") or []:
        try:
            if q.get("price"):
                out[str(q["symbol"])] = float(q["price"])
        except (TypeError, ValueError):
            continue
    for sym, res in dict(scan_artifact.get("results") or {}).items():
        checked = _parse(res.get("checked_at"))
        if checked is None or now - checked > timedelta(hours=3):
            continue
        per_tf = res.get("per_tf") or {}
        close = (per_tf.get("1h") or {}).get("last_close") or (per_tf.get("1d") or {}).get("last_close")
        if close:
            out.setdefault(str(sym), float(close))
    return out


def _append_ledger(rows: list[dict]) -> None:
    if not rows:
        return
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _track(state: dict, forecasts: Mapping[str, dict], prices: Mapping[str, float], cfg: Mapping[str, Any], now: datetime) -> dict:
    open_ = list(state.get("open") or [])
    created = resolved = 0
    for f in forecasts.values():
        if f["direction"] == "neutral" or f["strength"] < cfg["min_track_strength"]:
            continue
        price = prices.get(f["symbol"])
        if not price:
            continue
        recent = any(o["symbol"] == f["symbol"] and o["direction"] == f["direction"]
                     and now - (_parse(o["created_at"]) or now) < timedelta(hours=12) for o in open_)
        if recent:
            continue
        open_.append({"id": hashlib.sha1(f"{f['symbol']}|{_iso(now)}".encode()).hexdigest()[:12],
                      "symbol": f["symbol"], "kind": f["kind"], "direction": f["direction"],
                      "strength": f["strength"], "price": price, "created_at": _iso(now), "done": []})
        created += 1
    keep: list[dict] = []
    rows: list[dict] = []
    max_h = max(cfg["resolve_hours"] or [72])
    for o in open_:
        start = _parse(o["created_at"]) or now
        for h in cfg["resolve_hours"]:
            if h in o["done"] or now < start + timedelta(hours=h):
                continue
            p = prices.get(o["symbol"])
            if not p:
                continue
            ret = (p / o["price"] - 1.0) * 100.0 * (1 if o["direction"] == "up" else -1)
            outcome = "hit" if ret > _FLAT_PCT else "miss" if ret < -_FLAT_PCT else "flat"
            rows.append({"id": o["id"], "symbol": o["symbol"], "kind": o["kind"], "direction": o["direction"],
                         "strength": o["strength"], "horizon_h": h, "ret_pct": round(ret, 3),
                         "outcome": outcome, "created_at": o["created_at"], "resolved_at": _iso(now)})
            o["done"].append(h)
            resolved += 1
        if len(o["done"]) < len(cfg["resolve_hours"]) and now < start + timedelta(hours=2 * max_h):
            keep.append(o)
    state["open"] = keep[-_MAX_OPEN:]
    _append_ledger(rows)
    return {"created": created, "resolved": resolved, "open": len(state["open"])}


def scorecard(max_rows: int = 5000) -> dict:
    """Ufuk × tür × güç kovası isabet karnesi (çözülmüş öngörülerden)."""
    rows: list[dict] = []
    try:
        lines = _ledger_path().read_text(encoding="utf-8").splitlines()[-max_rows:]
        rows = [json.loads(line) for line in lines if line.strip()]
    except (OSError, ValueError):
        rows = []

    def agg(items: list[dict]) -> dict:
        hits = sum(1 for r in items if r["outcome"] == "hit")
        misses = sum(1 for r in items if r["outcome"] == "miss")
        n = hits + misses
        return {"n": len(items), "hits": hits, "misses": misses,
                "hit_rate": round(hits / n, 3) if n else None,
                "avg_ret_pct": round(sum(r["ret_pct"] for r in items) / len(items), 3) if items else None}

    by_h: dict[str, dict] = {}
    for h in sorted({r["horizon_h"] for r in rows}):
        sub = [r for r in rows if r["horizon_h"] == h]
        by_h[f"{h}h"] = {
            "all": agg(sub),
            "by_kind": {k: agg([r for r in sub if r["kind"] == k]) for k in sorted({r["kind"] for r in sub})},
            "by_strength": {
                label: agg([r for r in sub if lo <= r["strength"] < hi])
                for label, lo, hi in (("25-50", 25, 50), ("50-75", 50, 75), ("75-100", 75, 101))
            },
        }
    return {"resolved_total": len(rows), "horizons": by_h,
            "note": "Az örnekte oran gürültülüdür; öngörü karara bağlanmaz (owner kararı gerekir)."}


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "headlines": {}, "web": {}, "open": [], "forecasts": {}}


def _web_targets(scan_artifact: Mapping[str, Any], assets: Mapping[str, dict], web_state: Mapping[str, Any],
                 cfg: Mapping[str, Any], now: datetime) -> list[dict]:
    """En güçlü keşif adayları: güncel sinyaller (EV'ye göre) + kısa listeler."""
    ranked: list[str] = []
    results = dict(scan_artifact.get("results") or {})
    signals = sorted((r for r in results.values() if r.get("verdict") == "WOULD_OPEN_LONG"),
                     key=lambda r: -(r.get("expected_value") or 0))
    ranked += [str(r["symbol"]) for r in signals]
    for key in ("commodity_universe", "crypto_universe"):
        ranked += [str(c["symbol"]) for c in (scan_artifact.get(key) or {}).get("candidates") or []]
    out: list[dict] = []
    for sym in dict.fromkeys(ranked):
        a = assets.get(sym)
        if not a or a.get("registry"):
            continue
        last = _parse((web_state.get(sym) or {}).get("searched_at"))
        if last and now - last < timedelta(hours=cfg["web_interval_hours"]):
            continue
        out.append(a)
        if len(out) >= cfg["web_max_assets"]:
            break
    return out


def run(
    now: datetime | None = None,
    *,
    scan_artifact: Mapping[str, Any] | None = None,
    discovery_cfg: Mapping[str, Any] | None = None,
    recent_snapshots: Callable[[int], list[dict]] | None = None,
    web_search: Callable[..., Any] | None = None,
    source_table: Mapping[str, Any] | None = None,
    llm_headlines: Callable[[], list[dict]] | None = None,
) -> dict:
    """Learning worker adımı. Durumu yazar; özet döner (hata turu düşürmez — çağıran yakalar)."""
    from packages.discovery import scanner

    now = now or datetime.now(UTC)
    discovery_cfg = discovery_cfg if discovery_cfg is not None else scanner.load_config()
    cfg = config(discovery_cfg)
    art = scan_artifact if scan_artifact is not None else scanner._load_artifact()
    state = _load_state()
    store: dict[str, dict] = dict(state.get("headlines") or {})

    docs = (recent_snapshots or snapshot_store.recent)(cfg["snapshots_per_run"])
    added_rss = _ingest_snapshot_headlines(store, docs, now)
    reclassified = _reclassify(store)
    if llm_headlines is None:
        from packages.discovery import news_discovery

        llm_headlines = news_discovery.llm_headlines
    added_llm = _ingest_llm(store, llm_headlines(), now)

    assets = build_assets(art, discovery_cfg, cfg)
    web_state = dict(state.get("web") or {})
    added_web, web_errors = 0, []
    if web_search is None:
        from packages.agent.llm import web_search as ws

        web_search = ws.search
    for a in _web_targets(art, assets, web_state, cfg, now):
        res = web_search(_web_query(a), topic="news", time_range="week", max_results=cfg["web_max_results"])
        err = getattr(res, "error", None)
        web_state[a["symbol"]] = {"searched_at": _iso(now), "error": err,
                                  "hits": len(getattr(res, "results", None) or [])}
        if err:
            web_errors.append(err)
            if err in {"missing_api_key"}:
                break  # anahtar yok → bu turda başka arama denenmez
            continue
        added_web += _ingest_web(store, a, getattr(res, "results", None) or [], now)

    cutoff = now - timedelta(hours=cfg["window_hours"])
    store = {k: h for k, h in store.items() if (_parse(h.get("ts")) or now) >= cutoff}
    if len(store) > _MAX_HEADLINES:
        store = dict(sorted(store.items(), key=lambda kv: kv[1]["ts"])[-_MAX_HEADLINES:])

    table = source_table if source_table is not None else _load_source_table()
    headlines = list(store.values())
    forecasts = {}
    for sym, a in assets.items():
        f = forecast_for(a, headlines, table, now, cfg["half_life_hours"])
        if f is not None:
            forecasts[sym] = f

    latest = docs[0] if docs else None
    tracking = _track(state, forecasts, current_prices(art, latest, now), cfg, now)
    state.update({"schema_version": SCHEMA_VERSION, "generated_at": _iso(now), "headlines": store,
                  "web": web_state, "forecasts": forecasts})
    write_text_atomic(_state_path(), json.dumps(state, ensure_ascii=False, default=str))
    return {"status": "OK", "headlines": len(store), "added_rss": added_rss, "added_web": added_web,
            "added_llm": added_llm, "reclassified": reclassified,
            "web_errors": web_errors[:3], "forecasts": len(forecasts),
            "directional": sum(1 for f in forecasts.values() if f["direction"] != "neutral"), **tracking}


def load_forecasts() -> dict[str, dict]:
    return dict(_load_state().get("forecasts") or {})


def viewmodel() -> dict:
    state = _load_state()
    forecasts = sorted((state.get("forecasts") or {}).values(), key=lambda f: -f["strength"])
    return {"generated_at": state.get("generated_at"), "headlines": len(state.get("headlines") or {}),
            "forecasts": forecasts, "scorecard": scorecard(), "mode": "observe_only"}


__all__ = ["build_assets", "config", "forecast_for", "load_forecasts", "run", "scorecard",
           "source_weight", "viewmodel"]
