"""Dış kanıt katmanı (owner kararı 2026-10-30) — karara GİRMEZ, yalnız kanıt.

Ücretsiz kaynaklar:
- FRED: kredi ve stres (yüksek getiri spread'i, St. Louis stres endeksi, Chicago
  finansal koşullar), enflasyon beklentisi, Fed bilançosu, ters repo, geniş dolar;
  ayrıca önümüzdeki 14 günün önemli ABD açıklama takvimi.
- ABD Hazinesi FiscalData: Hazine nakit hesabı (TGA).
- Türetilmiş: net likidite = Fed bilançosu − TGA − ters repo.
- CFTC COT: altın, gümüş, bakır, WTI, BTC/ETH ve S&P vadelilerinde spekülatif
  (non-commercial) net pozisyon.
- GDELT: jeopolitik ve enerji temalı küresel haber tonu.
- Alternative.me: kripto Korku/Açgözlülük endeksi.

Öğrenme turunda çağrılır; her kaynak kendi aralığıyla yenilenir (dakikalar değil
saatler/günler), sonuç ``data/runtime/external_evidence.json``'a yazılır. Kaynak
hata verirse son iyi veri ``stale`` etiketiyle korunur; uydurma değer üretilmez.
Karar zincirine bağlanması ayrı bir owner kararıdır (gölge-önce).
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.ops.store import write_text_atomic

TIMEOUT_SEC = 15.0
_UA = "clean-e-yay/1.0 (paper research; read-only)"

FRED_SERIES: dict[str, str] = {
    "BAMLH0A0HYM2": "Yüksek getiri tahvil spread'i (%)",
    "STLFSI4": "St. Louis finansal stres endeksi",
    "NFCI": "Chicago finansal koşullar endeksi",
    "T10YIE": "10 yıllık enflasyon beklentisi (%)",
    "WALCL": "Fed bilançosu (milyon $)",
    "RRPONTSYD": "Gecelik ters repo (milyar $)",
    "DTWEXBGS": "Geniş dolar endeksi",
}
CALENDAR_KEYWORDS = (
    "Consumer Price Index", "Employment Situation", "Producer Price Index",
    "Gross Domestic Product", "Personal Income and Outlays", "Retail",
    "Job Openings", "FOMC", "Employment Cost Index", "Unemployment Insurance Weekly Claims",
)
CFTC_MARKETS: dict[str, str] = {
    "088691": "XAUUSD",
    "084691": "XAGUSD",
    "085692": "COPPER",
    "067651": "WTI",
    "133741": "BTCUSD",
    "146021": "ETHUSD",
    "13874A": "SP500",
}
GDELT_THEMES: dict[str, str] = {
    "jeopolitik": "(sanctions OR missile OR airstrike OR invasion) sourcelang:english",
    "enerji": "(opec OR \"oil supply\" OR pipeline OR refinery) sourcelang:english",
}
# Kaynak başına yenileme aralığı (saniye).
TTL_SEC: dict[str, float] = {
    "fred_series": 6 * 3600,
    "fred_calendar": 6 * 3600,
    "treasury_tga": 6 * 3600,
    "cftc_cot": 24 * 3600,
    "gdelt_tone": 3600,
    "fear_greed": 6 * 3600,
}
# Hata sonrası yeniden deneme beklemesi. GDELT 5 sn kuralını katı uygular ve
# 2026-10-30'da bu IP'ye boş yanıt / 429 veriyordu: uzun bekleme, az gürültü.
RETRY_AFTER_ERROR_SEC = 1800.0
RETRY_AFTER_ERROR_BY_SOURCE: dict[str, float] = {"gdelt_tone": 6 * 3600}


def _path() -> Path:
    return Path(os.environ.get("EXTERNAL_EVIDENCE_PATH", "data/runtime/external_evidence.json"))


def _ctx() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=_ctx()) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN dışla


# --------------------------------------------------------------------- FRED
def fetch_fred_series(get: Callable[[str], Any] = _get_json) -> dict:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY yok")
    out: dict[str, dict] = {}
    for series_id, label in FRED_SERIES.items():
        qs = urllib.parse.urlencode({
            "series_id": series_id, "sort_order": "desc", "limit": 60, "file_type": "json", "api_key": key,
        })
        obs = [o for o in (get(f"https://api.stlouisfed.org/fred/series/observations?{qs}").get("observations") or [])
               if _num(o.get("value")) is not None]
        if not obs:
            continue
        latest = obs[0]
        latest_day = date.fromisoformat(latest["date"])
        earlier = next((o for o in obs if date.fromisoformat(o["date"]) <= latest_day - timedelta(days=28)), None)
        value = _num(latest["value"])
        prev = _num(earlier["value"]) if earlier else None
        out[series_id] = {
            "label": label,
            "date": latest["date"],
            "value": value,
            "change_4w": round(value - prev, 4) if value is not None and prev is not None else None,
        }
    if not out:
        raise RuntimeError("FRED serisi dönmedi")
    return out


def fetch_fred_calendar(get: Callable[[str], Any] = _get_json, *, today: date | None = None) -> list[dict]:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY yok")
    start = today or datetime.now(UTC).date()
    qs = urllib.parse.urlencode({
        "realtime_start": start.isoformat(), "realtime_end": (start + timedelta(days=14)).isoformat(),
        "include_release_dates_with_no_data": "true", "order_by": "release_date", "sort_order": "asc",
        "limit": 1000, "file_type": "json", "api_key": key,
    })
    rows = get(f"https://api.stlouisfed.org/fred/releases/dates?{qs}").get("release_dates") or []
    seen: set[tuple[str, str]] = set()
    out = []
    for row in rows:
        name = str(row.get("release_name") or "")
        if not any(k in name for k in CALENDAR_KEYWORDS):
            continue
        item = (str(row.get("date")), name)
        if item in seen:
            continue
        seen.add(item)
        out.append({"date": item[0], "release": name, "release_id": row.get("release_id")})
    return out


# ------------------------------------------------------------------ Treasury
def fetch_treasury_tga(get: Callable[[str], Any] = _get_json) -> dict:
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
           "operating_cash_balance?sort=-record_date&page%5Bsize%5D=60")
    rows = [r for r in (get(url).get("data") or []) if "Closing Balance" in str(r.get("account_type"))]
    values = [(r["record_date"], _num(r.get("open_today_bal"))) for r in rows if _num(r.get("open_today_bal")) is not None]
    if not values:
        raise RuntimeError("TGA kapanış bakiyesi yok")
    latest_day, latest = values[0]
    week = next((v for d, v in values if date.fromisoformat(d) <= date.fromisoformat(latest_day) - timedelta(days=7)), None)
    return {
        "date": latest_day,
        "tga_musd": latest,
        "change_1w_musd": round(latest - week, 1) if week is not None else None,
    }


# ---------------------------------------------------------------------- CFTC
def fetch_cftc_cot(get: Callable[[str], Any] = _get_json) -> dict:
    codes = ",".join(f"'{c}'" for c in CFTC_MARKETS)
    qs = urllib.parse.urlencode({
        "$where": f"cftc_contract_market_code in({codes})",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": len(CFTC_MARKETS) * 3,
    })
    rows = get(f"https://publicreporting.cftc.gov/resource/6dca-aqww.json?{qs}") or []
    by_code: dict[str, list[dict]] = {}
    for row in rows:
        by_code.setdefault(str(row.get("cftc_contract_market_code")), []).append(row)
    out: dict[str, dict] = {}
    for code, symbol in CFTC_MARKETS.items():
        hist = by_code.get(code) or []
        if not hist:
            continue

        def _net(r: dict) -> tuple[float | None, float | None]:
            long_, short, oi = (_num(r.get(k)) for k in (
                "noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all"))
            if long_ is None or short is None:
                return None, None
            net = long_ - short
            return net, (round(100.0 * net / oi, 2) if oi else None)

        net, pct = _net(hist[0])
        prev, _ = _net(hist[1]) if len(hist) > 1 else (None, None)
        out[symbol] = {
            "market": hist[0].get("market_and_exchange_names"),
            "report_date": str(hist[0].get("report_date_as_yyyy_mm_dd") or "")[:10],
            "noncomm_net": net,
            "noncomm_net_pct_oi": pct,
            "change_1w": (net - prev) if net is not None and prev is not None else None,
        }
    if not out:
        raise RuntimeError("COT satırı yok")
    return out


# --------------------------------------------------------------------- GDELT
def fetch_gdelt_tone(get: Callable[[str], Any] = _get_json, *, sleep: Callable[[float], None] = time.sleep) -> dict:
    out: dict[str, dict] = {}
    for i, (theme, query) in enumerate(GDELT_THEMES.items()):
        if i:
            sleep(6.0)  # GDELT: en fazla 5 sn'de bir istek
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": query, "mode": "timelinetone", "timespan": "3d", "format": "json"}))
        series = (get(url).get("timeline") or [{}])[0].get("data") or []
        points = [_num(p.get("value")) for p in series if _num(p.get("value")) is not None]
        if not points:
            continue
        last_day = points[-96:]  # 15 dakikalık noktalar → son 24 saat
        out[theme] = {
            "latest": round(points[-1], 3),
            "avg_24h": round(sum(last_day) / len(last_day), 3),
            "avg_3d": round(sum(points) / len(points), 3),
            "points": len(points),
        }
    if not out:
        raise RuntimeError("GDELT ton verisi yok")
    return out


# ---------------------------------------------------------------- Fear&Greed
def fetch_fear_greed(get: Callable[[str], Any] = _get_json) -> dict:
    rows = get("https://api.alternative.me/fng/?limit=8&format=json").get("data") or []
    values = [_num(r.get("value")) for r in rows if _num(r.get("value")) is not None]
    if not rows or not values:
        raise RuntimeError("Korku/Açgözlülük verisi yok")
    return {
        "value": values[0],
        "classification": rows[0].get("value_classification"),
        "date": datetime.fromtimestamp(int(rows[0].get("timestamp", 0)), tz=UTC).date().isoformat(),
        "avg_7d": round(sum(values[:7]) / len(values[:7]), 1),
    }


FETCHERS: dict[str, Callable[[], Any]] = {
    "fred_series": fetch_fred_series,
    "fred_calendar": fetch_fred_calendar,
    "treasury_tga": fetch_treasury_tga,
    "cftc_cot": fetch_cftc_cot,
    "gdelt_tone": fetch_gdelt_tone,
    "fear_greed": fetch_fear_greed,
}


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _net_liquidity(sources: dict) -> dict | None:
    fred = (sources.get("fred_series") or {}).get("data") or {}
    tga = (sources.get("treasury_tga") or {}).get("data") or {}
    walcl = (fred.get("WALCL") or {}).get("value")
    rrp = (fred.get("RRPONTSYD") or {}).get("value")
    tga_v = tga.get("tga_musd")
    if walcl is None or rrp is None or tga_v is None:
        return None
    return {
        "value_musd": round(walcl - tga_v - rrp * 1000.0, 1),
        "formula": "Fed bilançosu − TGA − ters repo",
        "inputs": {"walcl_date": fred["WALCL"]["date"], "tga_date": tga.get("date"), "rrp_date": fred["RRPONTSYD"]["date"]},
    }


def refresh(*, now: datetime | None = None, fetchers: dict[str, Callable[[], Any]] | None = None) -> dict:
    """Vadesi gelen kaynakları yenile, artefaktı yaz, son durumu döndür."""
    current = now or datetime.now(UTC)
    state = load()
    sources: dict = dict(state.get("sources") or {})
    changed = False
    for name, fetch in (fetchers or FETCHERS).items():
        row = dict(sources.get(name) or {})
        last_try = row.get("attempted_at")
        if row.get("status") == "error":
            wait = RETRY_AFTER_ERROR_BY_SOURCE.get(name, RETRY_AFTER_ERROR_SEC)
        else:
            wait = TTL_SEC.get(name, 6 * 3600)
        if last_try:
            try:
                if (current - datetime.fromisoformat(last_try)).total_seconds() < wait:
                    continue
            except ValueError:
                pass
        row["attempted_at"] = current.isoformat()
        try:
            row.update(status="ok", data=fetch(), fetched_at=current.isoformat(), error=None)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            # Son iyi veri korunur ama bayat işaretlenir; yeni değer uydurulmaz.
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:160]}")
            if row.get("data") is not None:
                row["stale"] = True
        else:
            row.pop("stale", None)
        sources[name] = row
        changed = True
    out = {
        "generated_at": current.isoformat(),
        "decision_usage": "evidence_only",
        "sources": sources,
        "net_liquidity": _net_liquidity(sources),
    }
    if changed or not state:
        try:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, json.dumps(out, ensure_ascii=False, indent=1))
        except (OSError, TypeError, ValueError):
            pass
    return out


__all__ = ["FETCHERS", "TTL_SEC", "load", "refresh"]
