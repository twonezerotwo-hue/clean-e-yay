"""Bölge-planı gölge yürütücüsü (SALT-ANALİZ / read-only; canlıya dokunmaz).

Owner'ın el-çizimi kesişim-bölgesi yöntemi (öğretim seansı 2026-07-11, BTCUSD
haftalık). İŞBÖLÜMÜ BİLİNÇLİ: bölgeleri OWNER çizer (`config/zone_plans.yaml`)
— sistem bölge ÜRETMEZ (touche dersi: owner'ın gözü sabit formüle sığmıyor;
mekanikleşen yalnız uygulama disiplini). Bu modül owner'ın dallı planını
barlarda uçtan uca gölge-yürütür:

- **Dal 1 (çekirdek):** çekirdek bandında PARÇALI long (`entry_parts`
  eşit-aralıklı seviye; low değince seviyeden dolum).
- **BE kuralı:** bölge üstüne kapanış → break-even silahlanır; fiyat ortalama
  girişe geri sararsa TAMAMI 0 zararla çıkar. Sonra bölge üstünde
  `kalici_closes` ardışık kapanış → yeniden giriş (Dal 1B).
- **Dal 2a:** bölge altına düşüşte STOP YOK (owner: "fiyat geri retest'e
  gelecektir"); çekirdek ile derin katman arası İŞLEM-YOK; derin seviyede
  pozisyon BÜYÜTÜLÜR (ortalama düşürme). Derin lot, kırılan çekirdeğin alttan
  retest'inde TP olur (seviyeden seviyeye).
- **Dal 2b:** kırılan bölgenin üstüne `kalici_closes` ardışık kapanış → YÜKSEK
  BAKİYE ekleme (`reclaim_size_mult`) + TÜM pozisyona sert stop: çekirdek
  altının `reclaim_stop_pct` altı. Destek kırıldıktan sonra BE rejimi biter
  (owner'ın 2a/2b kuralları devralır).
- **Çıkış makinesi:** tepe→ortalama-giriş arasına LOG fib (owner fib'leri log
  çeker; grafik değerleriyle birebir doğrulandı); 0,236'ya kadar tüm pozisyon
  taşınır, sonra HER fib basamağında eşit parça TP + trailing bir alt basamağa
  (kapanış-bazlı; sabit yüzde DEĞİL). Basamak-0'ın bir altı = ortalama giriş,
  yani BE kuralı merdivenin doğal tabanı. Ortalama değişince (ekleme / derin-
  lot TP) merdiven yeniden çapalanır.

Tanımsız bırakılan durumlar (owner kuralı yok → makine BEKLER, uydurmaz):
BE-çıkışı sonrası derine düşüş; derin katmanın da kırılması (pozisyon taşınır,
max_drawdown_pct raporda görünür — riskin fotoğrafı karneye düşer).

Config-flag YOK (ölü-flag yasağı; `zero_two_strategy` deseni): salt-analiz,
karara/paper'a/ağırlığa dokunmaz. Interval-kapılı (günlük). Plan dosyası yoksa
no-op. Karne ileri-veriyle büyür: `valid_from` bugünse artifact önce WAIT
gösterir; owner geçmiş döngüler için tarihî plan eklerse geriye dönük ölçülür.
"""
from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

_ENGINE = "zone_plan_shadow_v1"
_INTERVAL_ENV = "ZONE_PLAN_SHADOW_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 24 * 3600
_PLANS_ENV = "ZONE_PLANS_PATH"
_DEFAULT_PLANS = "config/zone_plans.yaml"
_EVENT_CAP = 60

# Owner çıkış cetveli: her basamakta eşit parça TP, 1.0 = tepe (kalan hepsi).
_DEFAULT_TP_LEVELS = (0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def _path() -> Path:
    return Path(os.environ.get("ZONE_PLAN_SHADOW_PATH", "data/runtime/zone_plan_shadow.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


def log_fib(a: float, b: float, level: float) -> float:
    """`a` (0) → `b` (1) arasında LOG-ölçekli fib seviyesi.

    Owner fib'leri log çeker: 126.230,09→44.048,58 üstünde 0,236 = 56.472,68
    (grafikteki basılı değer) — lineer hesap tutmaz, log birebir tutar."""
    return 10 ** (math.log10(a) + level * (math.log10(b) - math.log10(a)))


def _norm_plan(p: dict) -> dict:
    """Ham YAML kaydını doğrula/normalize et; katman sırası bozuksa ValueError."""
    core = sorted(float(x) for x in p["core"])
    plan = {
        "id": str(p.get("id") or f"{p['symbol']}_{core[0]:.0f}"),
        "symbol": str(p["symbol"]),
        "timeframe": str(p.get("timeframe") or "1d"),
        "top": float(p["top"]),
        "core_low": core[0],
        "core_high": core[1],
        "deep": float(p["deep"]),
        "entry_parts": max(1, int(p.get("entry_parts", 3))),
        "deep_add_mult": float(p.get("deep_add_mult", 1.0)),
        "reclaim_size_mult": float(p.get("reclaim_size_mult", 2.0)),
        "reclaim_stop_pct": float(p.get("reclaim_stop_pct", 0.03)),
        "kalici_closes": max(1, int(p.get("kalici_closes", 5))),
        "tp_levels": tuple(float(x) for x in (p.get("tp_levels") or _DEFAULT_TP_LEVELS)),
        "valid_from": str(p.get("valid_from") or ""),
        "note": str(p.get("note") or ""),
    }
    if not (0 < plan["deep"] < plan["core_low"] < plan["core_high"] < plan["top"]):
        raise ValueError("katman sırası bozuk (0 < deep < core < top olmalı)")
    return plan


def load_plans() -> list[dict]:
    """`config/zone_plans.yaml` → geçerli plan listesi. Asla raise etmez."""
    try:
        p = Path(os.environ.get(_PLANS_ENV, _DEFAULT_PLANS))
        if not p.exists():
            return []
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        plans = []
        for item in raw.get("plans") or []:
            try:
                plans.append(_norm_plan(dict(item)))
            except (KeyError, TypeError, ValueError):
                continue
        return plans
    except (OSError, yaml.YAMLError):
        return []


def simulate(bars: list, plan: dict) -> dict:
    """Owner'ın dallı planını barlarda uçtan uca gölge-yürüt.

    Muhasebe LİNEER notional: lot = (giriş, boyut); pnl = Σ boyut·(çıkış−giriş).
    Böylece "ortalama girişten çıkış = tam 0 zarar" (BE kuralı) kuruşuna tutar.
    Yüzde raporu referansa göre: ref = 1.0 birim · çekirdek-orta fiyatı.
    Aynı barda stop VE hedef değerse stop önce işler (muhafazakâr)."""
    from_ts = None
    if plan.get("valid_from"):
        try:
            from_ts = datetime.fromisoformat(plan["valid_from"])
            if from_ts.tzinfo is None:
                from_ts = from_ts.replace(tzinfo=UTC)
        except ValueError:
            from_ts = None

    core_low, core_high, top = plan["core_low"], plan["core_high"], plan["top"]
    parts = plan["entry_parts"]
    if parts == 1:
        entry_levels = [(core_low + core_high) / 2]
    else:
        step = (core_high - core_low) / (parts - 1)
        entry_levels = [core_high - i * step for i in range(parts)]
    part_size = 1.0 / parts
    ref = (core_low + core_high) / 2  # yüzde-normalizasyon çıpası

    lots: list[list] = []            # [giriş, boyut, "core"|"deep"|"reclaim"]
    filled = [False] * parts
    realized = 0.0
    events: list[dict] = []
    phase = "WAIT"
    be_armed = False
    be_exited = False                # BE sonrası çekirdek limitleri yeniden dolmaz (1B tek yol)
    support_broken = False
    deep_added = False
    reclaim_done = False
    reclaim_stop: float | None = None
    kalici_n = 0                     # bölge-üstü ardışık kapanış sayacı (1B/2b ortak)
    rungs: list[float] = []
    rung_i = -1
    max_dd = 0.0
    done = False
    last_close: float | None = None

    def _ev(ts, name: str, price: float, note: str = "") -> None:
        events.append({"ts": ts.isoformat(), "event": name,
                       "price": round(price, 2), "note": note})

    def _avg() -> float | None:
        s = sum(lot[1] for lot in lots)
        return (sum(lot[0] * lot[1] for lot in lots) / s) if s > 0 else None

    def _open() -> float:
        return sum(lot[1] for lot in lots)

    def _rearm_ladder() -> None:
        nonlocal rungs, rung_i
        a = _avg()
        rungs = [log_fib(a, top, lv) for lv in plan["tp_levels"]] if a else []
        rung_i = -1

    def _close_all(price: float) -> None:
        nonlocal realized, lots
        for e, s, _tag in lots:
            realized += s * (price - e)
        lots = []

    for b in bars:
        if from_ts is not None and b.ts < from_ts:
            continue
        if done:
            break
        last_close = b.close

        # 1) Çekirdek dolumları — yalnız ilk iniş (BE sonrası limitler geri konmaz,
        #    destek kırıldıktan sonra bandın içinden geçiş dolum sayılmaz).
        if not be_exited and not support_broken:
            new_fill = False
            for i, lv in enumerate(entry_levels):
                if not filled[i] and b.low <= lv:
                    filled[i] = True
                    lots.append([lv, part_size, "core"])
                    _ev(b.ts, "CORE_FILL", lv, f"parça {i + 1}/{parts}")
                    new_fill = True
            if new_fill:
                phase = "CORE"
                _rearm_ladder()

        # 2) Derin katman: ortalama düşürme (Dal 2a; yalnız pozisyon açıkken, bir kez)
        if lots and support_broken and not deep_added and b.low <= plan["deep"]:
            lots.append([plan["deep"], plan["deep_add_mult"], "deep"])
            deep_added = True
            _rearm_ladder()
            _ev(b.ts, "DEEP_ADD", plan["deep"],
                f"ortalama düşürüldü → {_avg():.2f}")

        # 3) Sert stop (Dal 2b sonrası): tüm pozisyon desteğin %X altında kapanır
        if lots and reclaim_stop is not None and b.low <= reclaim_stop:
            _close_all(reclaim_stop)
            phase = "RECLAIM_STOPPED"
            _ev(b.ts, "HARD_STOP", reclaim_stop, "geri-alım stopu çalıştı")
            done = True

        # 4) BE stop (yalnız çekirdek rejimi: destek sağlam + merdiven başlamadı)
        if (lots and be_armed and rung_i < 0 and not support_broken
                and not reclaim_done):
            a = _avg()
            if a is not None and b.low <= a:
                _close_all(a)  # lineer muhasebede tam 0
                be_armed = False
                be_exited = True
                kalici_n = 0
                phase = "BE_EXIT"
                _ev(b.ts, "BE_EXIT", a, "0 zararla çıkış; 1B kalıcılık bekleniyor")

        # 5) Derin lotun retest TP'si: kırılan çekirdek alttan test edilince
        if lots and deep_added and b.high >= core_low:
            deep_lots = [lot for lot in lots if lot[2] == "deep"]
            if deep_lots:
                for lot in deep_lots:
                    realized += lot[1] * (core_low - lot[0])
                    lots.remove(lot)
                _rearm_ladder()
                _ev(b.ts, "RETEST_TP", core_low, "derin lot retest'te kapandı")

        # 6) Merdiven TP'leri: her basamakta kalanın eşit parçası; son basamak = hepsi
        while lots and rungs and rung_i + 1 < len(rungs) and b.high >= rungs[rung_i + 1]:
            rung_i += 1
            price = rungs[rung_i]
            open_sz = _open()
            slice_sz = open_sz if rung_i == len(rungs) - 1 else open_sz / (len(rungs) - rung_i)
            a = _avg()
            realized += slice_sz * (price - a)
            scale = 1.0 - slice_sz / open_sz
            for lot in lots:
                lot[1] *= scale
            if scale <= 1e-12:
                lots = []
            _ev(b.ts, "TP_RUNG", price,
                f"fib {plan['tp_levels'][rung_i]} — parça TP")
            if not lots:
                phase = "COMPLETED"
                _ev(b.ts, "PLAN_DONE", price, "merdiven tamamlandı")
                done = True

        # 7) Kapanış-bazlı kararlar
        if not done:
            # 7a) Merdiven trailing'i: bir alt basamağın altına kapanış → kalan çıkar
            if lots and rung_i >= 0:
                trail = rungs[rung_i - 1] if rung_i >= 1 else (_avg() or 0.0)
                if b.close < trail:
                    _close_all(b.close)
                    phase = "COMPLETED"
                    _ev(b.ts, "TRAIL_EXIT", b.close,
                        f"alt basamak ({trail:.2f}) altına kapanış")
                    done = True
            # 7b) BE silahlanması (çekirdek rejimi)
            if (lots and not be_armed and rung_i < 0 and not support_broken
                    and not reclaim_done and b.close > core_high):
                be_armed = True
                _ev(b.ts, "BE_ARMED", b.close, "bölge üstüne kapanış")
            # 7c) Destek kırılımı (Dal 2'ye geçiş; BE rejimi biter)
            if lots and not support_broken and b.close < core_low:
                support_broken = True
                be_armed = False
                phase = "UNDER_SUPPORT"
                _ev(b.ts, "SUPPORT_BREAK", b.close,
                    "çekirdek altı kapanış; derin katmana kadar işlem-yok")
            # 7d) Kalıcılık sayacı + 1B / 2b
            kalici_n = kalici_n + 1 if b.close > core_high else 0
            if kalici_n >= plan["kalici_closes"]:
                if phase == "BE_EXIT" and not lots:
                    lots.append([b.close, 1.0, "core"])
                    be_exited = False
                    kalici_n = 0
                    phase = "CORE"
                    _rearm_ladder()
                    _ev(b.ts, "REENTRY_1B", b.close,
                        f"{plan['kalici_closes']} kapanış bölge üstü — yeniden giriş")
                elif lots and support_broken and not reclaim_done:
                    lots.append([b.close, plan["reclaim_size_mult"], "reclaim"])
                    reclaim_done = True
                    reclaim_stop = core_low * (1.0 - plan["reclaim_stop_pct"])
                    kalici_n = 0
                    phase = "RECLAIMED"
                    _rearm_ladder()
                    _ev(b.ts, "RECLAIM_ADD", b.close,
                        f"yüksek bakiye; stop {reclaim_stop:.2f}")

        # 8) Sermaye eğrisi dibi (ortalama-düşürme dalının risk fotoğrafı)
        eq = realized + sum(s * (b.close - e) for e, s, _t in lots)
        max_dd = min(max_dd, eq)

    avg = _avg()
    unreal = sum(s * (last_close - e) for e, s, _t in lots) if lots and last_close else 0.0
    return {
        "state": phase,
        "filled_parts": sum(filled),
        "open_size": round(_open(), 4),
        "avg_entry": round(avg, 2) if avg else None,
        "last_close": round(last_close, 2) if last_close is not None else None,
        "realized_pct": round(realized / ref * 100, 2),
        "unrealized_pct": round(unreal / ref * 100, 2),
        "max_drawdown_pct": round(max_dd / ref * 100, 2),
        "rungs": [round(r, 2) for r in rungs],
        "rung_hit": rung_i,
        "entry_levels": [round(x, 2) for x in entry_levels],
        "events": events[-_EVENT_CAP:],
    }


def compute(now: datetime | None = None) -> dict:
    """Tüm owner planlarını arşiv+canlı barlarda yürüt. Asla raise etmez."""
    now = now or datetime.now(UTC)
    from packages.data.providers.ohlcv import get_bars, history

    plans_out = []
    for plan in load_plans():
        try:
            bars = history.merged(
                history.load(plan["symbol"], plan["timeframe"]),
                get_bars(plan["symbol"], plan["timeframe"]) or [],
            )
        except Exception:
            bars = []
        if not bars:
            plans_out.append({"id": plan["id"], "symbol": plan["symbol"],
                              "state": "NO_DATA", "note": plan["note"]})
            continue
        res = simulate(bars, plan)
        plans_out.append({
            "id": plan["id"], "symbol": plan["symbol"],
            "timeframe": plan["timeframe"], "note": plan["note"],
            "params": {k: plan[k] for k in (
                "top", "core_low", "core_high", "deep", "entry_parts",
                "deep_add_mult", "reclaim_size_mult", "reclaim_stop_pct",
                "kalici_closes", "valid_from")},
            **res,
        })
    return {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "plans": plans_out,
        "note": (
            "SALT-ANALIZ: owner'in el-cizimi bolge planlari golge yurutulur "
            "(bolgeler config/zone_plans.yaml'dan; sistem bolge URETMEZ). "
            "Canli karara/paper'a dokunmaz; kanit ileri-veriyle buyur."
        ),
    }


def _write(report: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def run_if_due() -> dict:
    """learning_worker adımı (interval-kapılı, günlük). Flag YOK (salt-analiz).
    Plan dosyası yok/boş → NO_PLANS (dosya yazılmaz; tam no-op)."""
    if not load_plans():
        return {"status": "NO_PLANS"}
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            if data.get("engine") == _ENGINE and 0 <= age < _interval_sec():
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = compute()
    _write(rep)
    states = [str(pl.get("state")) for pl in rep["plans"]]
    return {"status": "OK", "plans": len(rep["plans"]), "states": states}


def _load() -> dict | None:
    try:
        p = _path()
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def viewmodel() -> dict:
    """GET /learning/zone-plan — owner bölge-planı gölge karnesi (read-only).

    Her planı düz satıra çevirir: durum, dolan parça, ortalama giriş, gerçekleşen/
    açık PnL (çekirdek-orta referansına % olarak), sermaye-dibi, son olaylar.
    Panel HESAP YAPMAZ."""
    data = _load()
    if not data:
        return {"status": "NO_DATA", "generated_at": None, "plans": []}
    rows = []
    for pl in data.get("plans") or []:
        rows.append({
            "id": pl.get("id"),
            "symbol": pl.get("symbol"),
            "state": pl.get("state"),
            "filled_parts": pl.get("filled_parts", 0),
            "avg_entry": pl.get("avg_entry"),
            "last_close": pl.get("last_close"),
            "realized_pct": pl.get("realized_pct", 0.0),
            "unrealized_pct": pl.get("unrealized_pct", 0.0),
            "max_drawdown_pct": pl.get("max_drawdown_pct", 0.0),
            "entry_levels": pl.get("entry_levels") or [],
            "rungs": pl.get("rungs") or [],
            "events": (pl.get("events") or [])[-10:],
            "note": pl.get("note", ""),
        })
    return {
        "status": "OK",
        "generated_at": data.get("generated_at"),
        "engine": data.get("engine"),
        "plans": rows,
        "shadow_only": True,
    }


__all__ = [
    "compute",
    "load_plans",
    "log_fib",
    "run_if_due",
    "simulate",
    "viewmodel",
]
