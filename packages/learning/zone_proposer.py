"""Aday bölge önericisi (SALT-ANALİZ / read-only; canlıya dokunmaz).

Owner'ın el-çizimi kesişim yöntemini HERHANGİ bir asset'te mekanik GEOMETRİYLE
serer: haftalık pivotlar → LOG-uzayda trend çizgileri (owner log grafikte düz
çizer) → log-fib kümeleri → çizgi kesişimleri → "kaç bağımsız araç aynı fiyatta
hemfikir" (confluence) skoru → aday bölge listesi.

ÖNEMLİ SINIR (touche dersi, bkz [[project_touche_structural]]): makine bölge
SEÇMEZ, ADAY önerir. Owner'ın gözü sabit formüle sığmıyor — bu modül yalnız
geometriyi serer (pivot/çizgi/fib matematiği; taklit değil ölçüm), süzgeç ve
karar owner'da kalır. Kabul edilen aday `config/zone_plans.yaml`'a düşer,
`zone_plan_shadow` onu gölge-işletir. Kalibrasyon owner'ın kabul/ret geri
bildirimiyle olur; canlı karara bağlanmadan önce 5y çok-rejim testi ŞART.

Evren: rotasyon çekirdeği (BTC/altın/gümüş/S&P/tahvil/petrol/DXY — hepsi derin
tarihli) + yükselen sektör ETF'leri + keşif kısa listesi (discovery_scan.json,
zaten çekilmiş). Yalnız `ohlcv.get_bars` ile ucuz/cache'li erişilen semboller
işlenir (API-bütçe: alt-coin'lere kör tam-tarih çekilmez — evrene girince gelir).
İşlem AÇMAZ; canlı skora/karara/paper'a dokunmaz.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from packages.data.registry.loader import CONFIG_DIR
from packages.learning.zone_plan_shadow import log_fib

_ENGINE = "zone_proposer_v1"
_INTERVAL_ENV = "ZONE_PROPOSER_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 24 * 3600
_WEEK = timedelta(days=7)


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    kind: str  # "H" | "L"


@dataclass(frozen=True)
class Line:
    slope: float      # log10-fiyat / bar
    intercept: float  # log10-fiyat, bar 0'da
    kind: str         # "support" | "resistance"
    touches: int


# ---------------------------------------------------------------------------
# Saf geometri (test edilebilir, veri/ağ bağımsız)
# ---------------------------------------------------------------------------

def find_pivots(bars: list, span: int) -> list[Pivot]:
    """Fraktal pivotlar: ±`span` bar içinde en yüksek high = tepe, en düşük
    low = dip. Uçlar (span kadar) atlanır (komşuluk tamam değil)."""
    piv: list[Pivot] = []
    n = len(bars)
    for i in range(span, n - span):
        window = bars[i - span:i + span + 1]
        hi, lo = bars[i].high, bars[i].low
        if hi >= max(b.high for b in window) and hi > 0:
            piv.append(Pivot(i, hi, "H"))
        if lo <= min(b.low for b in window) and lo > 0:
            piv.append(Pivot(i, lo, "L"))
    return piv


def fit_log_line(i1: int, p1: float, i2: int, p2: float) -> tuple[float, float]:
    """İki (bar, fiyat) noktasından LOG-uzayda doğru: (eğim, kesişim)."""
    if i1 == i2 or p1 <= 0 or p2 <= 0:
        raise ValueError("geçersiz doğru noktaları")
    l1, l2 = math.log10(p1), math.log10(p2)
    slope = (l2 - l1) / (i2 - i1)
    return slope, l1 - slope * i1


def line_price_at(slope: float, intercept: float, i: float) -> float:
    """Doğrunun `i` barındaki fiyatı (log-uzaydan geri çevrilir)."""
    return 10 ** (slope * i + intercept)


def line_intersection(a: Line, b: Line) -> tuple[float, float] | None:
    """İki doğrunun kesişimi → (bar_index, fiyat). Paralel/ıraksamazsa None."""
    if abs(a.slope - b.slope) < 1e-12:
        return None
    i = (b.intercept - a.intercept) / (a.slope - b.slope)
    return i, line_price_at(a.slope, a.intercept, i)


def _best_line(bars: list, pivots: list[Pivot], kind: str, tol: float) -> Line | None:
    """`kind` sınırını en iyi çizen pivot-çiftini seç: dokunuş çok, ihlal az.

    support = dipleri birleştiren ALT sınır (barların low'u altına sarkmamalı);
    resistance = tepeleri birleştiren ÜST sınır. Log-uzayda tol=oransal band."""
    pts = [p for p in pivots if p.kind == ("L" if kind == "support" else "H")]
    if len(pts) < 2:
        return None
    ltol = math.log10(1 + tol)
    best: Line | None = None
    best_score = -1.0
    for a_i in range(len(pts)):
        for b_i in range(a_i + 1, len(pts)):
            pa, pb = pts[a_i], pts[b_i]
            try:
                slope, intercept = fit_log_line(pa.index, pa.price, pb.index, pb.price)
            except ValueError:
                continue
            touches = violations = 0
            for p in pts:
                d = math.log10(p.price) - (slope * p.index + intercept)
                if abs(d) <= ltol:
                    touches += 1
            for j, bar in enumerate(bars):
                line_log = slope * j + intercept
                if kind == "support":
                    if math.log10(max(bar.low, 1e-9)) < line_log - ltol:
                        violations += 1
                elif math.log10(bar.high) > line_log + ltol:
                    violations += 1
            score = touches - 0.5 * violations
            if score > best_score:
                best_score = score
                best = Line(slope, intercept, kind, touches)
    return best


def cluster_levels(levels: list[dict], tol: float) -> list[dict]:
    """Log-fiyat yakınlığındaki seviyeleri bölgelere kümele; her bölgeyi
    confluence (FARKLI kaynak-türü sayısı) ile skorla. `tol` = oransal band."""
    if not levels:
        return []
    ltol = math.log10(1 + tol)
    ordered = sorted(levels, key=lambda x: x["price"])
    zones: list[list[dict]] = [[ordered[0]]]
    for lv in ordered[1:]:
        anchor = zones[-1][0]["price"]
        if math.log10(lv["price"]) - math.log10(anchor) <= ltol:
            zones[-1].append(lv)
        else:
            zones.append([lv])
    out: list[dict] = []
    for members in zones:
        prices = [m["price"] for m in members]
        sources = {m["source"] for m in members}
        times = [m["at"] for m in members if m.get("at")]
        out.append({
            "low": round(min(prices), 4),
            "high": round(max(prices), 4),
            "mid": round(sum(prices) / len(prices), 4),
            "confluence": len(sources),
            "sources": sorted(sources),
            "members": [
                {"price": round(m["price"], 4), "source": m["source"],
                 "detail": m.get("detail", "")}
                for m in sorted(members, key=lambda x: x["price"])
            ],
            "at": min(times) if times else None,
        })
    return out


def analyze_bars(bars: list, cfg: dict) -> dict:
    """Bir asset'in haftalık barlarından aday bölge listesi (saf hesap).

    Pool = trend çizgileri (şimdi + ufuk) + çizgi kesişimi + log-fib retracement
    (makro salınım) + log-fib uzantı (son inen bacak) + tarihî yatay pivotlar.
    Confluence ≥ min_confluence bölgeler döner (skor sonra fiyata yakınlık)."""
    span = int(cfg.get("pivot_span", 6))
    if len(bars) < int(cfg.get("min_weekly_bars", 30)) + 2 * span:
        return {"status": "INSUFFICIENT", "weekly_bars": len(bars), "zones": []}

    pivots = find_pivots(bars, span)
    highs = [p for p in pivots if p.kind == "H"]
    lows = [p for p in pivots if p.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return {"status": "INSUFFICIENT", "weekly_bars": len(bars), "zones": []}

    n = len(bars)
    last_i = n - 1
    price_now = bars[-1].close
    t0 = bars[0].ts
    horizon = int(cfg.get("horizon_bars", 26))
    tol = float(cfg.get("cluster_tol_pct", 2.5)) / 100.0

    def _date(i: float) -> str:
        return (t0 + i * _WEEK).date().isoformat()

    pool: list[dict] = []
    # Çizilebilir geometri — grafik katmanı (zone_chart) bunu AYNEN çizer;
    # owner öneriyi gerçek grafik üstünde görüp onaylar/reddeder.
    draw: dict = {
        "horizon": horizon,
        "lines": [],
        "cross": None,
        "fib_retr": None,
        "fib_ext": None,
        "pivots": [
            {"i": p.index, "price": round(p.price, 6), "kind": p.kind}
            for p in pivots
        ],
    }
    support = _best_line(bars, pivots, "support", tol)
    resistance = _best_line(bars, pivots, "resistance", tol)

    for line, name in ((support, "support_line"), (resistance, "resistance_line")):
        if line is None:
            continue
        draw["lines"].append({
            "kind": name, "slope": line.slope,
            "intercept": line.intercept, "touches": line.touches,
        })
        for i, tag in ((last_i, "şimdi"), (last_i + horizon, f"+{horizon}h")):
            pool.append({
                "price": line_price_at(line.slope, line.intercept, i),
                "source": name, "detail": f"{tag} ({line.touches} dokunuş)",
                "at": _date(i),
            })

    # Çizgi kesişimi (owner'ın fiyat×ZAMAN karar noktası) — yalnız makul gelecek.
    if support is not None and resistance is not None:
        x = line_intersection(support, resistance)
        if x is not None:
            xi, xp = x
            if last_i - n <= xi <= last_i + horizon * 3 and xp > 0:
                draw["cross"] = {"i": round(xi, 1), "price": round(xp, 6),
                                 "date": _date(xi)}
                pool.append({
                    "price": xp, "source": "line_cross",
                    "detail": f"destek×direnç ({_date(xi)})", "at": _date(xi),
                })

    # Makro retracement (en yüksek tepe → en düşük dip).
    hi = max(highs, key=lambda p: p.price)
    lo = min(lows, key=lambda p: p.price)
    if hi.price > lo.price:
        retr_levels = cfg.get("retr_levels", [0.236, 0.382, 0.5, 0.618, 0.786])
        draw["fib_retr"] = {
            "low": round(lo.price, 6), "high": round(hi.price, 6),
            "levels": {str(lv): round(log_fib(lo.price, hi.price, float(lv)), 6)
                       for lv in retr_levels},
        }
        for lv in retr_levels:
            pool.append({
                "price": log_fib(lo.price, hi.price, float(lv)),
                "source": "fib_retr", "detail": f"{lv} (makro {lo.price:.0f}-{hi.price:.0f})",
                "at": None,
            })

    # Uzantı (son TAMAMLANMIŞ inen bacak: son tepe → sonraki son dip).
    last_high = max(highs, key=lambda p: p.index)
    lows_after = [p for p in lows if p.index > last_high.index]
    if lows_after:
        leg_lo = min(lows_after, key=lambda p: p.price)
        if last_high.price > leg_lo.price:
            ext_levels = cfg.get("ext_levels", [1.236, 1.414, 1.618])
            draw["fib_ext"] = {
                "from": round(last_high.price, 6), "to": round(leg_lo.price, 6),
                "levels": {str(lv): round(log_fib(last_high.price, leg_lo.price, float(lv)), 6)
                           for lv in ext_levels},
            }
            for lv in ext_levels:
                pool.append({
                    "price": log_fib(last_high.price, leg_lo.price, float(lv)),
                    "source": "fib_ext",
                    "detail": f"{lv} (bacak {last_high.price:.0f}-{leg_lo.price:.0f})",
                    "at": None,
                })

    # Tarihî yatay pivotlar (kırılan seviye = gelecekteki S/R — owner reuse eder).
    for p in pivots:
        pool.append({
            "price": p.price, "source": "prior_pivot",
            "detail": f"{'tepe' if p.kind == 'H' else 'dip'} @bar{p.index}",
            "at": None,
        })

    min_conf = int(cfg.get("min_confluence", 2))
    zones = [z for z in cluster_levels(pool, tol) if z["confluence"] >= min_conf]
    # prior_pivot TEK başına confluence sayılmasın (yatay seviye bol olur):
    # en az bir "hesaplanan" kaynak (çizgi/fib/kesişim) şart.
    calc = {"support_line", "resistance_line", "line_cross", "fib_retr", "fib_ext"}
    zones = [z for z in zones if calc.intersection(z["sources"])]

    for z in zones:
        z["dist_pct"] = round((z["mid"] / price_now - 1) * 100, 2)
        z["side"] = "altında" if z["mid"] < price_now else "üstünde"
    zones.sort(key=lambda z: (-z["confluence"], abs(z["dist_pct"])))

    max_zones = int(cfg.get("max_zones", 5))
    return {
        "status": "OK",
        "weekly_bars": len(bars),
        "price_now": round(price_now, 4),
        "pivots": {"highs": len(highs), "lows": len(lows)},
        "support_touches": support.touches if support else 0,
        "resistance_touches": resistance.touches if resistance else 0,
        "zones": zones[:max_zones],
        "draw": draw,
    }


# ---------------------------------------------------------------------------
# Orkestrasyon (evren + veri; asla raise etmez)
# ---------------------------------------------------------------------------

def _cfg() -> dict:
    try:
        p = Path(os.environ.get("ZONE_PROPOSER_PATH_CFG", str(CONFIG_DIR / "zone_proposer.yaml")))
        return dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError):
        return {}


def _path() -> Path:
    return Path(os.environ.get("ZONE_PROPOSER_PATH", "data/runtime/zone_proposer.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


def _universe(cfg: dict) -> list[dict]:
    """Taranacak adaylar [{symbol, cg_id?}] — makro çekirdek + KEŞİF EVRENİ.

    Owner kararı (2026-07-12): keşif tarayıcısının bulduğu adaylar da taranır —
    "analiz sabit, varlık değişken" ilkesi bu katmana da uygulanır. Kaynaklar:
    (1) rotasyon çekirdeği (derin tarih), (2) owner ekleri, (3) keşif artifact'ı:
    yükselen sektör ETF'leri + KRİPTO KISA LİSTESİ (cg_id ile — artık statik
    haritada olmayan alt-coin'ler de girer) + canlı sinyal sembolleri (ETF'ler
    get_bars ile; kripto ancak cg_id biliniyorsa). Keşif kaynaklı aday sayısı
    `discovery_max` ile sınırlı (API bütçesi: tarayıcı aynı 1d barları zaten
    çekiyor — TTL cache çoğu çağrıyı bedavaya getirir)."""
    from packages.data.providers.rotation.engine import ROTATION_SYMBOLS

    cands: list[dict] = [{"symbol": s} for s in dict.fromkeys(ROTATION_SYMBOLS.values())]
    cands.extend({"symbol": str(s)} for s in (cfg.get("extra_symbols") or []))
    if cfg.get("discovery_candidates", True):
        try:
            from packages.discovery import scanner as _sc
            art = _sc._load_artifact()
            disc: list[dict] = []
            cg_map: dict[str, str] = {}
            for c in ((art.get("crypto_universe") or {}).get("candidates") or []):
                sym, cg = str(c.get("symbol") or ""), str(c.get("cg_id") or "")
                if sym and cg:
                    cg_map[sym] = cg
                    disc.append({"symbol": sym, "cg_id": cg})
            for c in (art.get("rising_sectors") or []):
                if c.get("symbol"):
                    disc.append({"symbol": str(c["symbol"])})
            # Canlı sinyal sembolleri (results'tan): ETF'ler get_bars ile ucuz;
            # kripto ancak kısa-liste cg_id'si biliniyorsa (kör çağrı yok).
            results = art.get("results") or {}
            for sym in (art.get("signal_symbols") or []):
                kind = str((results.get(sym) or {}).get("kind") or "")
                if kind == "sector_etf":
                    disc.append({"symbol": str(sym)})
                elif sym in cg_map:
                    disc.append({"symbol": str(sym), "cg_id": cg_map[sym]})
            max_disc = int(cfg.get("discovery_max", 10))
            seen = {c["symbol"] for c in cands}
            added = 0
            for c in disc:
                if c["symbol"] in seen or added >= max_disc:
                    continue
                seen.add(c["symbol"])
                cands.append(c)
                added += 1
        except Exception:
            pass
    return cands


def _weekly_bars(symbol: str, cg_id: str | None = None) -> list:
    """1d barları arşiv+canlı birleştir → haftalığa resample.

    `cg_id` verilirse (keşif kripto adayı — statik haritada yok) 1d barlar
    CoinGecko fetch_by_ticker ile gelir (TTL-throttle'lı; tarayıcıyla aynı yol)."""
    from packages.data.providers.ohlcv import get_bars, history, resample

    try:
        if cg_id:
            from packages.data.providers.ohlcv import coingecko as _cg
            live = _cg.fetch_by_ticker(cg_id, symbol, "1d") or []
        else:
            live = get_bars(symbol, "1d") or []
        daily = history.merged(history.load(symbol, "1d"), live)
    except Exception:
        return []
    daily = [b for b in daily if getattr(b, "verified", True)]
    if not daily:
        return []
    return resample.resample(daily, "1w")


def compute(now: datetime | None = None) -> dict:
    """Tüm evreni tara → asset başına aday bölge listesi. Asla raise etmez."""
    now = now or datetime.now(UTC)
    cfg = _cfg()
    assets = []
    for cand in _universe(cfg):
        symbol = cand["symbol"]
        bars = _weekly_bars(symbol, cand.get("cg_id"))
        res = analyze_bars(bars, cfg) if bars else {"status": "NO_DATA", "zones": []}
        assets.append({"symbol": symbol, **res})
    assets.sort(key=lambda a: (
        -(a["zones"][0]["confluence"] if a.get("zones") else 0),
    ))
    return {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "assets": assets,
        "note": (
            "SALT-ANALIZ: owner kesisim yontemini mekanik geometriyle serer "
            "(pivot/log-cizgi/log-fib/kesisim → confluence). Makine bolge SECMEZ, "
            "ADAY onerir; owner suzer, kabul edileni zone_plans.yaml'a koyar. "
            "Canli karara dokunmaz."
        ),
    }


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _zones_overlap(a: dict, b: dict, tol: float = 0.01) -> bool:
    return not (a["high"] * (1 + tol) < b["low"] or b["high"] * (1 + tol) < a["low"])


def _notify_new_zones(prev: dict | None, rep: dict, cfg: dict) -> int:
    """Owner uyarısı: YENİ güçlü kesişim bölgesi → dashboard bildirimi.

    Yalnız önceki artifact'ta OLMAYAN (örtüşmeyen) ve confluence ≥
    `notify_min_confluence` bölgeler için; ilk koşu (prev yok) sessizdir —
    deploy sonrası bildirim seli olmaz. Asla raise etmez; bildirim hatası
    taramayı durduramaz."""
    if not prev:
        return 0
    try:
        from packages.notifications import Notification, append_many, make_id

        min_conf = int(cfg.get("notify_min_confluence", 4))
        prev_zones: dict[str, list[dict]] = {
            str(a.get("symbol")): list(a.get("zones") or [])
            for a in (prev.get("assets") or [])
        }
        max_per_run = int(cfg.get("notify_max_per_run", 5))
        notes: list = []
        for a in rep.get("assets") or []:
            sym = str(a.get("symbol"))
            for z in a.get("zones") or []:
                if len(notes) >= max_per_run:
                    break
                if z["confluence"] < min_conf:
                    continue
                if any(_zones_overlap(z, pz) for pz in prev_zones.get(sym, [])):
                    continue
                title = f"{sym}: yeni kesişim bölgesi ★{z['confluence']}"
                body = (
                    f"{z['low']:.2f}–{z['high']:.2f} bandında {z['confluence']} "
                    f"bağımsız araç kesişiyor ({', '.join(z['sources'])}); fiyata "
                    f"uzaklık %{z['dist_pct']} ({z['side']}). İptal edilmedikçe "
                    "onaylı — panelden incele (katman 2, Bölge Önerileri)."
                )
                notes.append(Notification(
                    id=make_id("zone_candidate"),
                    ts=datetime.now(UTC).isoformat(),
                    type="zone_candidate",
                    priority="medium",
                    title=title,
                    body_short=title,
                    body_long=body,
                ))
        if notes:
            append_many(notes)
        return len(notes)
    except Exception:
        return 0


def run_if_due() -> dict:
    """learning_worker adımı (interval-kapılı, günlük). Flag YOK (salt-analiz).

    Kendini-onarma: hiçbir asset'i OK olmayan artifact (ör. sağlayıcı limiti /
    ağ kesintisi anına denk gelen koşu) TAZE SAYILMAZ — bir sonraki koşu yeniden
    dener; bozuk koşu 24 saat kilitleyemez. Yeni güçlü bölge → owner bildirimi."""
    prev: dict | None = None
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            prev = data
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            usable = any(
                a.get("status") == "OK" for a in (data.get("assets") or [])
            )
            if data.get("engine") == _ENGINE and usable and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = compute()
    _write(rep)
    notified = _notify_new_zones(prev, rep, _cfg())
    with_zones = sum(1 for a in rep["assets"] if a.get("zones"))
    return {"status": "OK", "assets": len(rep["assets"]),
            "with_zones": with_zones, "notified": notified}


def _load() -> dict | None:
    try:
        p = _path()
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def viewmodel() -> dict:
    """GET /learning/zone-proposer — aday bölge önerileri (read-only, hesap YAPMAZ).

    Her asset için en güçlü confluence bölgeleri: fiyat bandı, kaç bağımsız araç
    kesişiyor, hangi araçlar, fiyata uzaklık, (varsa) yaklaşık tarih + owner onay
    durumu (`verdict`: owner iptal etmedikçe 'onayli' — zone_approval defteri)."""
    from packages.learning import zone_approval

    data = _load()
    if not data:
        return {"status": "NO_DATA", "generated_at": None, "assets": []}
    rows = []
    for a in data.get("assets") or []:
        if not a.get("zones"):
            continue
        sym = str(a.get("symbol"))
        zones = [
            {**z, "verdict": zone_approval.verdict_for(sym, z["low"], z["high"])}
            for z in a["zones"]
        ]
        rows.append({
            "symbol": sym,
            "price_now": a.get("price_now"),
            "weekly_bars": a.get("weekly_bars"),
            "top_confluence": zones[0]["confluence"],
            "zones": zones,
        })
    return {
        "status": "OK",
        "generated_at": data.get("generated_at"),
        "engine": data.get("engine"),
        "honesty": (
            "Makine ADAY önerir, bölge SEÇMEZ. Hiçbir öneriyle işlem açılmadı; "
            "owner süzer, kabul edileni zone_plans.yaml'a koyar."
        ),
        "assets": rows,
        "shadow_only": True,
    }


__all__ = [
    "Line",
    "Pivot",
    "analyze_bars",
    "cluster_levels",
    "compute",
    "find_pivots",
    "fit_log_line",
    "line_intersection",
    "line_price_at",
    "run_if_due",
    "viewmodel",
]
