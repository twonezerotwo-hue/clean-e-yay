"""Haber güdümlü keşif (owner kararı 2026-10-05, ikinci tur) — SALT-GÖZLEM.

Keşif kayıtlı ya da önceden listelenmiş varlıklarla sınırlı kalmaz:

1. **Ham akış:** tüm RSS kaynakları (piyasa + jeopolitik + konu kaynakları:
   tarım, madencilik, enerji, nakliye, yarı iletken, ilaç, ticaret politikası).
2. **Çıkarım (yerel YZ):** Ollama modeli her başlık grubundan fiyatı gerçekten
   etkileyecek olayları, doğuracakları sonucu ve etkilenecek işlem gören
   varlıkları (emtia vadelisi, ETF, hisse, kripto, döviz) yön ve güvenle önerir.
3. **Doğrulama (deterministik):** önerilen sembol Yahoo'da var mı, türü uygun mu,
   adı tutuyor mu, yeterli geçmişi ve likiditesi var mı? Tutmazsa adla aranır.
   Uydurma/yanlış eşleme elenir ve sayılır.
4. **Aday defteri (72 sa):** doğrulanan varlıklar olay kanıtlarıyla birikir. Kayıtlı
   bir varlığa denk gelen sonuç aday olmaz; o varlığın haber öngörüsüne kanıt olur.

Keşif taraması yukarı yönlü adayları teknik analizden geçirir; haber öngörüsü ve Fikir
Panosu zinciri kanıt olarak kullanır. Hiçbir aşama işlem açmaz, işlem evrenine varlık
eklemez. YZ yalnız yerel modelle (ücretsiz) koşar ve ortak LLM bütçesini harcamaz;
yerel model yoksa (ör. AWS) adım atlanır.
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

from packages.ops.store import write_text_atomic

SCHEMA_VERSION = 1
ALLOWED_TYPES = {"EQUITY": "equity", "ETF": "etf", "FUTURE": "future", "CRYPTOCURRENCY": "crypto",
                 "CURRENCY": "fx"}
_US_EXCHANGES = {"NYQ", "NMS", "NGM", "NCM", "ASE", "PCX", "BTS", "NAS", "NYS", "CBO"}
_CONF_W = {"low": 0.5, "med": 1.0, "high": 1.5}
_NAME_STOP = {
    "inc", "corp", "corporation", "company", "ltd", "plc", "the", "trust", "fund", "etf", "shares",
    "share", "class", "holdings", "holding", "group", "usd", "index", "futures", "future", "spot",
    "price", "prices", "stock", "stocks", "and", "for", "ishares", "spdr", "vaneck", "invesco",
    "proshares", "global", "select", "sector", "international", "limited",
}
_SEEN_DAYS = 7
_RESOLVE_OK_DAYS = 7
_RESOLVE_BAD_DAYS = 2
_MAX_EVENTS = 300

FetchGroupFn = Callable[..., tuple[list[Any], int, str | None]]
FetchChartFn = Callable[[str], tuple[dict, list[Any]] | None]
SearchFn = Callable[[str], list[dict] | None]


def _path() -> Path:
    return Path(os.environ.get("NEWS_DISCOVERY_PATH", "data/runtime/news_discovery.json"))


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


def _parse(ts: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def _key(title: str) -> str:
    """news_forecast ile AYNI anahtar (başlık defterleri birleşebilsin)."""
    return hashlib.sha1(re.sub(r"\W+", " ", title.lower()).strip().encode("utf-8")).hexdigest()[:16]


def config(discovery_cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if discovery_cfg is None:
        from packages.discovery.scanner import load_config

        discovery_cfg = load_config()
    raw = dict(discovery_cfg.get("news_discovery") or {})
    return {
        "enabled": bool(raw.get("enabled", True)),
        "feed_refresh_min": float(raw.get("feed_refresh_min", 15)),
        "per_feed": int(raw.get("per_feed", 15)),
        "max_headline_age_hours": float(raw.get("max_headline_age_hours", 12)),
        "headlines_per_call": int(raw.get("headlines_per_call", 15)),
        "calls_per_run": int(raw.get("calls_per_run", 1)),
        "max_calls_per_day": int(raw.get("max_calls_per_day", 300)),
        "max_output_tokens": int(raw.get("max_output_tokens", 700)),
        "max_events_per_call": int(raw.get("max_events_per_call", 4)),
        "max_assets_per_event": int(raw.get("max_assets_per_event", 3)),
        "max_new_resolutions_per_run": int(raw.get("max_new_resolutions_per_run", 8)),
        "candidate_ttl_hours": float(raw.get("candidate_ttl_hours", 72)),
        "half_life_hours": float(raw.get("half_life_hours", 24)),
        "max_candidates": int(raw.get("max_candidates", 15)),
        "min_scan_strength": int(raw.get("min_scan_strength", 20)),
        "min_dollar_volume": float(raw.get("min_dollar_volume", 5_000_000)),
        "min_daily_bars": int(raw.get("min_daily_bars", 31)),
        "extra_feeds": [dict(f) for f in raw.get("extra_feeds") or [] if f and f.get("url")],
    }


# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------

def _empty() -> dict:
    return {"schema_version": SCHEMA_VERSION, "generated_at": None, "pool": {"fetched_at": None, "items": []},
            "seen": {}, "resolved": {}, "events": [], "calls": {"day": None, "n": 0}, "stats": {}}


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {**_empty(), **data}
    except (OSError, ValueError):
        pass
    return _empty()


def _save(state: Mapping[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(state, ensure_ascii=False, default=str))


def _prune(state: dict, cfg: Mapping[str, Any], now: datetime) -> None:
    def fresh(ts: Any, days: float) -> bool:
        t = _parse(ts)
        return t is not None and now - t <= timedelta(days=days)

    state["seen"] = {k: v for k, v in dict(state.get("seen") or {}).items() if fresh(v, _SEEN_DAYS)}
    state["resolved"] = {
        k: v for k, v in dict(state.get("resolved") or {}).items()
        if fresh(v.get("at"), _RESOLVE_BAD_DAYS if v.get("status") == "rejected" else _RESOLVE_OK_DAYS)
    }
    ttl = cfg["candidate_ttl_hours"] / 24.0
    state["events"] = [e for e in state.get("events") or [] if fresh(e.get("analyzed_at"), ttl)][-_MAX_EVENTS:]


# ---------------------------------------------------------------------------
# 1) Ham akış
# ---------------------------------------------------------------------------

def _feeds(cfg: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    from packages.data.providers.news import rss

    extra = tuple({"url": str(f["url"]), "source": str(f.get("source") or "Konu")} for f in cfg["extra_feeds"])
    return rss.MARKET_FEEDS + rss.GEO_FEEDS + extra


def _refresh_pool(state: dict, cfg: Mapping[str, Any], now: datetime, fetch_group: FetchGroupFn | None) -> dict:
    pool = dict(state.get("pool") or {})
    fetched = _parse(pool.get("fetched_at"))
    if fetched is not None and now - fetched < timedelta(minutes=cfg["feed_refresh_min"]):
        return {"status": "CACHED", "items": len(pool.get("items") or [])}
    if fetch_group is None:
        from packages.data.providers.news import rss

        fetch_group = rss.fetch_feed_group
    # geo=False: jeopolitik kaynaklarda da bölge süzgeci yok — sonucu olan her olay aday.
    heads, ok, err = fetch_group(_feeds(cfg), geo=False, max_items=cfg["per_feed"])
    items: dict[str, dict] = {}
    for h in heads:
        title = str(getattr(h, "title", "") or "").strip()
        ts = getattr(h, "ts", None)
        if not title or not isinstance(ts, datetime):
            continue
        items.setdefault(_key(title), {"key": _key(title), "title": title[:240],
                                       "source": str(getattr(h, "source", "") or ""), "ts": _iso(ts)})
    state["pool"] = {"fetched_at": _iso(now), "items": list(items.values()), "feeds_ok": ok, "last_error": err}
    return {"status": "FETCHED", "items": len(items), "feeds_ok": ok}


def _pending(state: Mapping[str, Any], cfg: Mapping[str, Any], now: datetime) -> list[dict]:
    """İşlenmemiş taze başlıklar: en yeni önce, kaynaklar arasında sırayla (tek kaynak boğmasın)."""
    seen = dict(state.get("seen") or {})
    max_age = timedelta(hours=cfg["max_headline_age_hours"])
    by_source: dict[str, list[dict]] = {}
    for it in (state.get("pool") or {}).get("items") or []:
        ts = _parse(it.get("ts"))
        if it["key"] in seen or ts is None or now - ts > max_age:
            continue
        by_source.setdefault(it.get("source") or "", []).append(it)
    queues = [sorted(v, key=lambda x: x["ts"], reverse=True) for _, v in sorted(by_source.items())]
    out: list[dict] = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


# ---------------------------------------------------------------------------
# 2) Yerel YZ çıkarımı
# ---------------------------------------------------------------------------

SYSTEM = (
    "Sen bir piyasa etki analistisin. Haber başlıklarından olayın doğuracağı somut sonucu ve bu sonuçtan "
    "fiyatı etkilenecek İŞLEM GÖREN varlıkları çıkarırsın. Uydurma yapma; emin değilsen o başlığı atla. "
    "Bu bir işlem emri değildir; yalnız keşif adayı önerirsin."
)

_PROMPT = (
    "Başlıklar:\n{titles}\n\n"
    "Görev: Yalnız fiyatları GERÇEKTEN etkileyebilecek en önemli en fazla {max_events} başlığı seç. "
    "Her biri için en fazla {max_assets} varlık ver. Endeks değil işlem gören araç ver (S&P 500 yerine SPY). "
    "Yönü sonucun varlığın FİYATINA etkisine göre ver (ör. getiriler yükselirse tahvil fonu düşer). "
    "Sembol Yahoo Finance biçiminde: vadeli 'KC=F', ETF 'COPX', hisse 'FCX', kripto 'SOL-USD', döviz 'EURUSD=X'. "
    "Sonucu Türkçe ve kısa yaz (en fazla 14 kelime). Yalnız JSON:\n"
    '{{"e":[{{"h":<başlık no>,"c":"<sonuç>","a":[{{"t":"<sembol>","n":"<varlık adı>","d":"up|down","k":"low|med|high"}}]}}]}}'
)


def _default_client() -> Any:
    """Yalnız yerel Ollama — uzak sağlayıcıya düşmez (kota/ücret yemez)."""
    from packages.agent.llm import client as llm

    if llm.get_mode() != "ollama":
        return None
    return llm.OllamaClient()


def _loads_salvage(text: str) -> dict | None:
    """JSON'u ayrıştır; kesikse son tam olay nesnesine kadar kurtar."""
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    for m in sorted((m.end() for m in re.finditer(r"\}\s*\]\s*\}", text)), reverse=True)[:40]:
        try:
            data = json.loads(text[:m] + "]}")
            if isinstance(data, dict):
                return data
        except ValueError:
            continue
    return None


def parse_extraction(text: str, n_titles: int, *, max_events: int = 4, max_assets: int = 3) -> list[dict] | None:
    """YZ çıktısı → [{h, c, a:[{t, n, d, k}]}]; ayrıştırılamazsa None."""
    data = _loads_salvage(text)
    if data is None:
        return None
    out: list[dict] = []
    used: set[int] = set()
    for ev in data.get("e") or data.get("events") or []:
        if not isinstance(ev, Mapping):
            continue
        try:
            h = int(ev.get("h"))
        except (TypeError, ValueError):
            continue
        if not 1 <= h <= n_titles or h in used:
            continue
        assets = []
        for a in ev.get("a") or []:
            if not isinstance(a, Mapping):
                continue
            t = str(a.get("t") or "").strip().upper().replace(" ", "")
            d = str(a.get("d") or "").strip().lower()
            k = str(a.get("k") or "med").strip().lower()
            k = "med" if k.startswith("med") else k
            if not t or len(t) > 15 or d not in ("up", "down"):
                continue
            assets.append({"t": t, "n": str(a.get("n") or "").strip()[:80], "d": d,
                           "k": k if k in _CONF_W else "med"})
        if not assets:
            continue
        used.add(h)
        out.append({"h": h, "c": str(ev.get("c") or "").strip()[:200], "a": assets[:max_assets]})
        if len(out) >= max_events:
            break
    return out


# ---------------------------------------------------------------------------
# 3) Doğrulama
# ---------------------------------------------------------------------------

def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) >= 3 and t not in _NAME_STOP}


def name_matches(llm_name: str, yahoo_name: str, ticker: str) -> bool:
    """YZ'nin verdiği ad Yahoo'daki adla örtüşüyor mu (FXY'yi 'Fed faizi' sanma gibi hataları eler)."""
    a = _tokens(llm_name)
    if a & _tokens(yahoo_name):
        return True
    base = re.split(r"[=\-.^]", ticker.upper())[0]
    return bool(base) and base.lower() in a


def symbol_for(ticker: str, asset_type: str, commodity_by_ticker: Mapping[str, str]) -> str:
    t = ticker.upper()
    if t in commodity_by_ticker:
        return commodity_by_ticker[t]
    if asset_type == "crypto" and t.endswith("-USD"):
        return t[:-4] + "USD"
    if asset_type == "fx" and t.endswith("=X"):
        return t[:-2]
    if asset_type == "future" and t.endswith("=F"):
        return t[:-2] + "_F"
    return re.sub(r"[^A-Z0-9]", "", t)


def registry_ticker_map() -> dict[str, str]:
    """Yahoo ticker / sembol → kayıtlı (işlem evreni) sembol."""
    from packages.data.providers.ohlcv import yfinance
    from packages.data.registry import assets as asset_registry
    from packages.data.registry import custom_assets

    out: dict[str, str] = {}
    for a in asset_registry.all_assets():
        sym = str(a.symbol).upper()
        out[sym] = sym
        ticker = yfinance._SYMBOL_MAP.get(sym) or custom_assets.ticker_for(sym, "yfinance")
        if ticker:
            out[ticker.upper()] = sym
        if getattr(a, "asset_class", "") == "crypto" and sym.endswith("USD"):
            out[f"{sym[:-3]}-USD"] = sym
    return out


def _metrics(bars: list[Any]) -> dict:
    closes = [float(b.close) for b in bars]
    last = closes[-1]

    def chg(n: int) -> float | None:
        return round((last / closes[-1 - n] - 1.0) * 100.0, 2) if len(closes) > n and closes[-1 - n] else None

    recent = bars[-20:]
    vols = [float(b.volume or 0.0) for b in recent]
    dollar = [float(b.close) * float(b.volume or 0.0) for b in recent]
    return {"price": round(last, 6), "chg_7d_pct": chg(5), "chg_30d_pct": chg(21),
            "avg_volume": sum(vols) / len(vols) if vols else 0.0,
            "avg_dollar_volume": sum(dollar) / len(dollar) if dollar else 0.0}


def _check(ticker: str, llm_name: str, chart: tuple[dict, list[Any]] | None, cfg: Mapping[str, Any],
           *, name_check: bool = True) -> tuple[dict | None, str]:
    if chart is None:
        return None, "sembol_yok"
    meta, bars = chart
    asset_type = ALLOWED_TYPES.get(str(meta.get("instrumentType") or "").upper())
    if asset_type is None:
        return None, f"tur_uygun_degil:{meta.get('instrumentType')}"
    if len(bars) < cfg["min_daily_bars"]:
        return None, "gecmis_yetersiz"
    yahoo_name = f"{meta.get('longName') or ''} {meta.get('shortName') or ''}".strip()
    if name_check and asset_type != "fx" and not name_matches(llm_name, yahoo_name, ticker):
        return None, "ad_uyusmuyor"
    m = _metrics(bars)
    if asset_type in ("equity", "etf") and m["avg_dollar_volume"] < cfg["min_dollar_volume"]:
        return None, "likidite_dusuk"
    if asset_type == "crypto" and m["avg_volume"] < cfg["min_dollar_volume"]:
        return None, "likidite_dusuk"
    return {"ticker": str(meta.get("symbol") or ticker).upper(), "asset_type": asset_type,
            "name": str(meta.get("longName") or meta.get("shortName") or llm_name)[:80],
            "exchange": meta.get("exchangeName"),
            **{k: m[k] for k in ("price", "chg_7d_pct", "chg_30d_pct")},
            "avg_dollar_volume": round(m["avg_dollar_volume"])}, "ok"


def resolve(proposal: Mapping[str, Any], state: dict, cfg: Mapping[str, Any], now: datetime, *,
            registry: Mapping[str, str], commodity_by_ticker: Mapping[str, str],
            fetch_chart: FetchChartFn, search: SearchFn, budget: list[int]) -> dict:
    """Önerilen varlığı doğrular. budget[0] = bu koşuda kalan yeni ağ doğrulaması."""
    ticker, llm_name = str(proposal["t"]).upper(), str(proposal.get("n") or "")
    if ticker in registry:
        return {"status": "registry", "symbol": registry[ticker], "ticker": ticker, "name": llm_name}
    cache = state.setdefault("resolved", {})
    ck = f"t:{ticker}|{llm_name.lower()}"
    if ck in cache:
        return {k: v for k, v in cache[ck].items() if k != "at"}
    if budget[0] <= 0:
        return {"status": "deferred", "ticker": ticker, "name": llm_name, "reason": "kota"}
    budget[0] -= 1
    info, reason = _check(ticker, llm_name, fetch_chart(ticker), cfg)
    if info is None and reason in ("sembol_yok", "ad_uyusmuyor") and llm_name:
        for q in search(llm_name) or []:
            t2 = str(q.get("symbol") or "").upper()
            q_type = ALLOWED_TYPES.get(str(q.get("type") or "").upper())
            if not t2 or q_type is None or not name_matches(llm_name, str(q.get("name") or ""), t2):
                continue
            if q_type in ("equity", "etf") and str(q.get("exchange") or "") not in _US_EXCHANGES:
                continue
            if t2 in registry:
                info, reason = {"registry": registry[t2], "ticker": t2}, "ok"
                break
            info, reason = _check(t2, llm_name, fetch_chart(t2), cfg)
            if info is not None:
                break
    if info is not None and info.get("registry"):
        out = {"status": "registry", "symbol": info["registry"], "ticker": info["ticker"], "name": llm_name}
    elif info is not None:
        out = {"status": "valid", "symbol": symbol_for(info["ticker"], info["asset_type"], commodity_by_ticker),
               **info}
        if out["symbol"] in registry.values():
            out = {"status": "registry", "symbol": out["symbol"], "ticker": info["ticker"], "name": info["name"]}
    else:
        out = {"status": "rejected", "ticker": ticker, "name": llm_name, "reason": reason}
    cache[ck] = {**out, "at": _iso(now)}
    return out


# ---------------------------------------------------------------------------
# 4) Aday defteri
# ---------------------------------------------------------------------------

def candidates(state: Mapping[str, Any], cfg: Mapping[str, Any], now: datetime) -> list[dict]:
    """Olaylardan doğrulanmış (kayıt dışı) adaylar; güce göre sıralı."""
    agg: dict[str, dict] = {}
    for ev in state.get("events") or []:
        t = _parse(ev.get("ts")) or _parse(ev.get("analyzed_at")) or now
        decay = math.exp(-math.log(2) * max(0.0, (now - t).total_seconds() / 3600.0) / cfg["half_life_hours"])
        for a in ev.get("assets") or []:
            if a.get("status") != "valid":
                continue
            c = agg.setdefault(a["symbol"], {
                "symbol": a["symbol"], "ticker": a["ticker"], "name": a.get("name"),
                "asset_type": a.get("asset_type"), "up_w": 0.0, "down_w": 0.0, "events": [],
                "first_seen": ev.get("analyzed_at"), "price": a.get("price"),
                "chg_7d_pct": a.get("chg_7d_pct"), "chg_30d_pct": a.get("chg_30d_pct"),
            })
            w = _CONF_W.get(a.get("confidence") or "med", 1.0) * decay
            c["up_w" if a.get("direction") == "up" else "down_w"] += w
            c["events"].append(ev["id"])
            c["last_seen"] = ev.get("analyzed_at")
    out = []
    for c in agg.values():
        score = c["up_w"] - c["down_w"]
        c["direction"] = "up" if score > 0.15 else "down" if score < -0.15 else "mixed"
        c["strength"] = min(100, round(abs(score) * 35))
        c["n_events"] = len(set(c["events"]))
        c["up_w"], c["down_w"] = round(c["up_w"], 3), round(c["down_w"], 3)
        out.append(c)
    out.sort(key=lambda c: (-c["strength"], -c["n_events"], c["symbol"]))
    return out[: cfg["max_candidates"]]


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------

def _commodity_by_ticker(discovery_cfg: Mapping[str, Any]) -> dict[str, str]:
    items = dict((discovery_cfg.get("commodities") or {}).get("items") or {})
    return {str(dict(m or {}).get("ticker") or "").upper(): str(sym) for sym, m in items.items()
            if dict(m or {}).get("ticker")}


def run(
    now: datetime | None = None,
    *,
    discovery_cfg: Mapping[str, Any] | None = None,
    client_factory: Callable[[], Any] | None = None,
    fetch_group: FetchGroupFn | None = None,
    fetch_chart: FetchChartFn | None = None,
    search: SearchFn | None = None,
    registry: Mapping[str, str] | None = None,
) -> dict:
    """Learning worker adımı: akışı tazele, sıradaki başlıkları YZ'ye sor, doğrula, defteri yaz."""
    now = now or datetime.now(UTC)
    if discovery_cfg is None:
        from packages.discovery.scanner import load_config

        discovery_cfg = load_config()
    cfg = config(discovery_cfg)
    if not cfg["enabled"]:
        return {"status": "DISABLED"}
    state = _load()
    _prune(state, cfg, now)
    pool = _refresh_pool(state, cfg, now, fetch_group)

    client = (client_factory or _default_client)()
    calls = dict(state.get("calls") or {})
    if calls.get("day") != now.date().isoformat():
        calls = {"day": now.date().isoformat(), "n": 0}
    stats = {"pool": pool, "llm_calls": 0, "screened": 0, "events": 0, "proposed": 0, "valid": 0,
             "registry": 0, "rejected": {}, "errors": []}
    status = "OK"
    if client is None:
        status = "LOCAL_LLM_OFF"
    elif calls["n"] >= cfg["max_calls_per_day"]:
        status = "DAILY_CAP"
    else:
        if fetch_chart is None or search is None:
            from packages.data.providers.ohlcv import yfinance

            fetch_chart = fetch_chart or yfinance.fetch_chart
            search = search or yfinance.search
        registry = registry if registry is not None else registry_ticker_map()
        commodity_by_ticker = _commodity_by_ticker(discovery_cfg)
        budget = [cfg["max_new_resolutions_per_run"]]
        pending = _pending(state, cfg, now)
        per_call = cfg["headlines_per_call"]
        for i in range(cfg["calls_per_run"]):
            batch = pending[i * per_call:(i + 1) * per_call]
            if not batch or calls["n"] >= cfg["max_calls_per_day"]:
                break
            prompt = _PROMPT.format(
                titles="\n".join(f"{j + 1}. {it['title']}" for j, it in enumerate(batch)),
                max_events=cfg["max_events_per_call"], max_assets=cfg["max_assets_per_event"],
            )
            try:
                comp = client.complete(SYSTEM, prompt, cfg["max_output_tokens"], 0.1, json_mode=True)
            except Exception as exc:  # yerel model hatası turu düşürmez
                stats["errors"].append(f"llm:{type(exc).__name__}")
                break
            calls["n"] += 1
            stats["llm_calls"] += 1
            if comp is None:
                stats["errors"].append("llm_unavailable")
                break  # başlıklar 'görüldü' sayılmaz → sonraki turda yeniden denenir
            parsed = parse_extraction(comp.text, len(batch), max_events=cfg["max_events_per_call"],
                                      max_assets=cfg["max_assets_per_event"])
            for it in batch:
                state["seen"][it["key"]] = _iso(now)
            stats["screened"] += len(batch)
            if parsed is None:
                stats["errors"].append("unparsed")
                continue
            for ev in parsed:
                head = batch[ev["h"] - 1]
                assets = []
                for prop in ev["a"]:
                    res = resolve(prop, state, cfg, now, registry=registry, commodity_by_ticker=commodity_by_ticker,
                                  fetch_chart=fetch_chart, search=search, budget=budget)
                    stats["proposed"] += 1
                    if res["status"] in ("valid", "registry"):
                        stats[res["status"]] += 1
                    elif res["status"] == "rejected":
                        r = str(res.get("reason") or "?").split(":")[0]
                        stats["rejected"][r] = stats["rejected"].get(r, 0) + 1
                    assets.append({**res, "proposed_ticker": prop["t"], "direction": prop["d"],
                                   "confidence": prop["k"]})
                state["events"].append({
                    "id": head["key"], "title": head["title"], "source": head["source"], "ts": head["ts"],
                    "consequence": ev["c"], "assets": assets, "analyzed_at": _iso(now),
                    "model": getattr(comp, "model", None),
                })
                stats["events"] += 1
    state["calls"] = calls
    state["generated_at"] = _iso(now)
    state["status"] = status
    state["candidates"] = candidates(state, cfg, now)
    state["stats"] = {**stats, "calls_today": calls["n"]}
    _save(state)
    return {"status": status, **{k: stats[k] for k in ("llm_calls", "screened", "events", "proposed", "valid",
                                                       "registry", "rejected", "errors")},
            "candidates": len(state["candidates"]), "pool": pool.get("items")}


# ---------------------------------------------------------------------------
# Okuyucular (scanner, news_forecast, ideas, API)
# ---------------------------------------------------------------------------

def scanner_candidates(discovery_cfg: Mapping[str, Any] | None = None) -> list[dict]:
    """Teknik analize girecek yukarı yönlü adaylar (ağsız; artifact'tan)."""
    cfg = config(discovery_cfg)
    rows = (_load().get("candidates") or [])
    return [
        {"symbol": c["symbol"], "ticker": c["ticker"], "name": c.get("name") or c["symbol"],
         "asset_type": c.get("asset_type"), "chg_7d_pct": c.get("chg_7d_pct"),
         "chg_30d_pct": c.get("chg_30d_pct"), "news_strength": c.get("strength")}
        for c in rows if c.get("direction") == "up" and int(c.get("strength") or 0) >= cfg["min_scan_strength"]
    ]


def all_candidates() -> list[dict]:
    return list(_load().get("candidates") or [])


def llm_headlines() -> list[dict]:
    """Haber öngörüsüne kanıt: YZ'nin bir varlığa bağladığı başlıklar (kayıtlı + aday)."""
    out = []
    for ev in _load().get("events") or []:
        impacts = {a["symbol"]: {"d": 1.0 if a["direction"] == "up" else -1.0, "k": a.get("confidence") or "med"}
                   for a in ev.get("assets") or [] if a.get("status") in ("valid", "registry") and a.get("symbol")}
        if impacts:
            out.append({"key": ev["id"], "title": ev["title"], "source": ev.get("source") or "",
                        "ts": ev.get("ts"), "consequence": ev.get("consequence"), "impacts": impacts})
    return out


def chains_for(symbols: Iterable[str], limit: int = 3) -> dict[str, list[dict]]:
    """Varlıkların haber zinciri: başlık → sonuç → yön (en yeni önce; defter bir kez okunur)."""
    wanted = set(symbols)
    out: dict[str, list[dict]] = {}
    for ev in reversed(_load().get("events") or []):
        for a in ev.get("assets") or []:
            sym = a.get("symbol")
            if sym not in wanted or a.get("status") not in ("valid", "registry"):
                continue
            rows = out.setdefault(sym, [])
            if len(rows) < limit and all(r["title"] != ev["title"] for r in rows):
                rows.append({"title": ev["title"], "source": ev.get("source"), "ts": ev.get("ts"),
                             "consequence": ev.get("consequence"), "direction": a.get("direction"),
                             "confidence": a.get("confidence")})
    return out


def chain_for(symbol: str, limit: int = 3) -> list[dict]:
    return chains_for([symbol], limit).get(symbol, [])


def viewmodel(limit_events: int = 12) -> dict:
    state = _load()
    events = []
    for ev in reversed(state.get("events") or []):
        shown = [
            {k: a.get(k) for k in ("symbol", "ticker", "name", "asset_type", "direction", "confidence", "status",
                                   "reason", "proposed_ticker")}
            for a in ev.get("assets") or []
        ]
        if not any(a["status"] in ("valid", "registry") for a in shown):
            continue
        events.append({"title": ev["title"], "source": ev.get("source"), "ts": ev.get("ts"),
                       "consequence": ev.get("consequence"), "analyzed_at": ev.get("analyzed_at"), "assets": shown})
        if len(events) >= limit_events:
            break
    stats = dict(state.get("stats") or {})
    return {
        "generated_at": state.get("generated_at"),
        "status": state.get("status") or "UNKNOWN",
        "events": events,
        "candidates": list(state.get("candidates") or []),
        "stats": {"calls_today": stats.get("calls_today", 0), "screened": stats.get("screened", 0),
                  "pool": (stats.get("pool") or {}).get("items"), "rejected": stats.get("rejected") or {}},
    }


__all__ = ["all_candidates", "candidates", "chain_for", "chains_for", "config", "llm_headlines", "name_matches",
           "parse_extraction", "registry_ticker_map", "resolve", "run", "scanner_candidates", "symbol_for",
           "viewmodel"]
