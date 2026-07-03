"""Çıkış Otopsisi (exit forensics) — kötü çıkışın NEREDE ve tahmini KAÇA
olduğunu ölçer (denetim paketi 2026-07-03, ölçüm ekseni).

Salt gözlem (observe-only): karar/ağırlık/geometri yoluna dokunmaz; learning
worker snapshot yazar, API okur, panel gösterir. tf_target_trainer Dilim 5'te
`trainer_evidence()` çıktısını (flag arkasında) adım-şiddeti kanıtı olarak
tüketebilir — veri yetersizse {} döner, trainer sabit adıma düşer (sahtelik yok).

DÜRÜSTLÜK KURALLARI (yalnız kayıtlı veriden hesaplanabilen):
- MAE/MFE yalnız pozisyon AÇIKKEN kaydedilir → kapanış-sonrası hiçbir şey
  hesaplanmaz ("stop olmasa TP'ye gider miydi" YOK — o veri mevcut değil).
- SL kapanışında mae_pct ≈ SL mesafesi → risk_pct yoksa vekil olarak kullanılır.
- $ değerleri TAHMİNİDİR: size_usd (D1) tercih; yoksa |pnl_pct| ≥ MIN_MOVE_PCT
  iken notional = |pnl / (pnl_pct/100)| çıkarımı; o da yoksa None ("—").
- Yalnız AUTO kohort (fingerprint + data_verified) puanlanır — manuel/test
  işlemler çıkış-makinesi karnesine giremez; şeffaflık sayacında görünür.
"""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from packages.learning import cohorts
from packages.learning import outcomes as outcomes_mod
from packages.learning.outcomes import CanonicalOutcome
from packages.learning.tf_target_trainer import _classify_close

# entry_exit_quality._MIN_MOVE_PCT deseni: bundan küçük hareket "hiç işlemedi".
MIN_MOVE_PCT = 0.05
# Bir bucket'ın konuşabilmesi için asgari kullanılabilir outcome sayısı.
MIN_BUCKET = 5
# SL'den önce >= 0.5R kârda idiyse "kâr geri verildi" (roundtrip) sayılır.
ROUNDTRIP_MIN_R = 0.5

_DEFAULT_SNAPSHOT_PATH = "data/runtime/exit_forensics.json"
HISTORY_MAX = 60


def snapshot_path() -> Path:
    """Env her çağrıda okunur (empirical_pwin._path deseni) — conftest'in
    session-tmp izolasyonu import sırasından bağımsız çalışır."""
    return Path(os.environ.get("EXIT_FORENSICS_OUT_PATH", _DEFAULT_SNAPSHOT_PATH))

_LIMITS = [
    "MFE/MAE yalnız pozisyon açıkken kaydedilir; kapanış sonrası fiyat bilinmez",
    "$ değerleri tahminidir (size_usd ya da notional çıkarımı)",
]


def _notional_usd(o: CanonicalOutcome) -> float | None:
    """Pozisyon büyüklüğü ($): size_usd (kesin) > notional çıkarımı > None."""
    if o.size_usd is not None and o.size_usd > 0:
        return float(o.size_usd)
    if o.pnl_pct is not None and abs(o.pnl_pct) >= MIN_MOVE_PCT and o.pnl:
        return abs(float(o.pnl) / (float(o.pnl_pct) / 100.0))
    return None


def _category(o: CanonicalOutcome) -> str:
    """MANUAL ayrı kategori (şeffaflık); gerisi tf_target_trainer eşlemesi."""
    if (o.close_reason or "").strip().upper().startswith("MANUAL"):
        return "manual"
    return _classify_close(o.close_reason)


def _diagnose(o: CanonicalOutcome) -> dict:
    """Tek AUTO outcome → dürüst çıkış teşhisi (kategoriye özgü maliyet)."""
    cat = _category(o)
    pnl_pct = float(o.pnl_pct) if o.pnl_pct is not None else None
    mfe = float(o.mfe_pct or 0.0)
    mae = float(o.mae_pct or 0.0)
    notional = _notional_usd(o)
    d: dict = {
        "category": cat,
        "pnl": float(o.pnl),
        "notional_usd": notional,
        "no_excursion": mfe <= 0.0 and mae <= 0.0,  # legacy: teşhis edilemez
        "capture": None,          # trailing kazananı: pnl/mfe (<=1)
        "give_back_pct": None,    # trailing + SL-roundtrip: tepeden geri verilen
        "give_back_usd_est": None,
        "missed_capture_pct": None,  # time_stop: bankaya konamayan tepe kâr
        "missed_usd_est": None,
        "never_worked": False,    # time_stop + mfe<=eşik → giriş sorunu
        "sl_class": None,         # sl: roundtrip | straight | gray
    }
    if d["no_excursion"] or pnl_pct is None:
        return d

    if cat == "trailing":
        if mfe > MIN_MOVE_PCT:
            d["give_back_pct"] = round(max(0.0, mfe - pnl_pct), 4)
            if notional is not None:
                d["give_back_usd_est"] = round(notional * d["give_back_pct"] / 100.0, 2)
            if pnl_pct > 0:
                d["capture"] = round(min(1.0, pnl_pct / mfe), 4)
    elif cat == "time_stop":
        if mfe <= MIN_MOVE_PCT:
            d["never_worked"] = True  # giriş/yön sorunu — çıkış maliyeti DEĞİL
        else:
            d["missed_capture_pct"] = round(max(0.0, mfe - max(pnl_pct, 0.0)), 4)
            if notional is not None:
                d["missed_usd_est"] = round(notional * d["missed_capture_pct"] / 100.0, 2)
    elif cat == "sl":
        mfe_r = (mfe / 100.0 / o.risk_pct) if (o.risk_pct and o.risk_pct > 0) else None
        roundtrip = (
            mfe_r >= ROUNDTRIP_MIN_R
            if mfe_r is not None
            # risk_pct yoksa: SL kapanışında mae ≈ SL mesafesi vekili.
            else (mae > 0 and mfe >= 0.5 * mae)
        )
        if mfe <= MIN_MOVE_PCT:
            d["sl_class"] = "straight"  # hiç işlemedi → giriş sorunu, maliyet yok
        elif roundtrip:
            d["sl_class"] = "roundtrip"  # açık kâr korunamadı → çıkış-makinesi hatası
            d["give_back_pct"] = round(max(0.0, mfe - pnl_pct), 4)
            if notional is not None:
                d["give_back_usd_est"] = round(notional * d["give_back_pct"] / 100.0, 2)
        else:
            d["sl_class"] = "gray"  # sayılır, maliyet atfedilmez
    # tp / manual / other: sayım + pnl yeterli (sahte "masada kalan" üretilmez).
    return d


def _empty_bucket() -> dict:
    return {
        "n": 0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "avg_capture": None,
        "avg_give_back_pct": None,
        "give_back_usd_est_total": None,
        "avg_missed_capture_pct": None,
        "missed_usd_est_total": None,
        "sl_roundtrip": 0,
        "sl_straight": 0,
        "sl_gray": 0,
        "never_worked": 0,
        "no_excursion": 0,
        "usd_est_covered_n": 0,
        "avg_mfe_pct": None,
        "top_module": None,
    }


def _finalize_bucket(b: dict, acc: dict) -> dict:
    n = b["n"]
    if n:
        b["total_pnl"] = round(b["total_pnl"], 2)
        b["avg_pnl"] = round(b["total_pnl"] / n, 2)
    if acc["captures"]:
        b["avg_capture"] = round(sum(acc["captures"]) / len(acc["captures"]), 4)
    if acc["give_backs"]:
        b["avg_give_back_pct"] = round(sum(acc["give_backs"]) / len(acc["give_backs"]), 4)
    if acc["gb_usd"]:
        b["give_back_usd_est_total"] = round(sum(acc["gb_usd"]), 2)
    if acc["missed"]:
        b["avg_missed_capture_pct"] = round(sum(acc["missed"]) / len(acc["missed"]), 4)
    if acc["missed_usd"]:
        b["missed_usd_est_total"] = round(sum(acc["missed_usd"]), 2)
    if acc["mfes"]:
        b["avg_mfe_pct"] = round(sum(acc["mfes"]) / len(acc["mfes"]), 4)
    if acc["module_cost"]:
        b["top_module"] = max(acc["module_cost"].items(), key=lambda kv: kv[1])[0]
    elif acc["module_n"]:
        b["top_module"] = max(acc["module_n"].items(), key=lambda kv: kv[1])[0]
    return b


def report(outcomes: list[CanonicalOutcome] | None = None) -> dict:
    """TF × kapanış-kategorisi çıkış otopsisi (AUTO kohort; observe-only)."""
    outs = outcomes if outcomes is not None else outcomes_mod.outcomes_from_state()
    auto: list[CanonicalOutcome] = []
    excl = {"manual": 0, "non_auto": 0}
    for o in outs:
        c = cohorts.classify(o)
        if c == cohorts.AUTO:
            auto.append(o)
        elif c == cohorts.MANUAL:
            excl["manual"] += 1
        else:
            excl["non_auto"] += 1

    buckets: dict[tuple[str, str], dict] = {}
    accs: dict[tuple[str, str], dict] = {}
    no_excursion_total = 0
    for o in auto:
        d = _diagnose(o)
        key = (o.timeframe or "?", d["category"])
        b = buckets.setdefault(key, _empty_bucket())
        acc = accs.setdefault(
            key,
            {
                "captures": [], "give_backs": [], "gb_usd": [],
                "missed": [], "missed_usd": [], "mfes": [],
                "module_cost": {}, "module_n": {},
            },
        )
        b["n"] += 1
        b["total_pnl"] += d["pnl"]
        mod = o.dominant_module or "unknown"
        acc["module_n"][mod] = acc["module_n"].get(mod, 0) + 1
        if d["no_excursion"]:
            b["no_excursion"] += 1
            no_excursion_total += 1
            continue
        if o.mfe_pct:
            acc["mfes"].append(float(o.mfe_pct))
        if d["capture"] is not None:
            acc["captures"].append(d["capture"])
        if d["give_back_pct"] is not None:
            acc["give_backs"].append(d["give_back_pct"])
        if d["give_back_usd_est"] is not None:
            acc["gb_usd"].append(d["give_back_usd_est"])
            b["usd_est_covered_n"] += 1
            acc["module_cost"][mod] = acc["module_cost"].get(mod, 0.0) + d["give_back_usd_est"]
        if d["missed_capture_pct"] is not None:
            acc["missed"].append(d["missed_capture_pct"])
        if d["missed_usd_est"] is not None:
            acc["missed_usd"].append(d["missed_usd_est"])
            b["usd_est_covered_n"] += 1
            acc["module_cost"][mod] = acc["module_cost"].get(mod, 0.0) + d["missed_usd_est"]
        if d["never_worked"]:
            b["never_worked"] += 1
        if d["sl_class"] == "roundtrip":
            b["sl_roundtrip"] += 1
        elif d["sl_class"] == "straight":
            b["sl_straight"] += 1
        elif d["sl_class"] == "gray":
            b["sl_gray"] += 1

    bucket_rows = [
        {"timeframe": tf, "category": cat, **_finalize_bucket(b, accs[(tf, cat)])}
        for (tf, cat), b in sorted(buckets.items())
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "cohort": "auto",
        "total": len(outs),
        "usable": len(auto),
        "min_bucket": MIN_BUCKET,
        "buckets": bucket_rows,
        "top_costs": _top_costs(bucket_rows),
        "excluded": {**excl, "no_excursion": no_excursion_total},
        "limits": list(_LIMITS),
    }


def _fmt_usd(v: float | None) -> str:
    return f"tahmini ${v:,.0f}" if v is not None else "$ bilinmiyor"


def _top_costs(bucket_rows: list[dict]) -> list[dict]:
    """En pahalı 3 çıkış hatası — Türkçe düz-dil kartlar (n >= MIN_BUCKET)."""
    cards: list[dict] = []
    for b in bucket_rows:
        if b["n"] < MIN_BUCKET:
            continue
        tf, cat = b["timeframe"], b["category"]
        if cat == "trailing" and b["avg_give_back_pct"]:
            usd = b["give_back_usd_est_total"]
            rank = usd if usd is not None else b["avg_give_back_pct"] * b["n"]
            cap = (
                f"kârın ort. %{(1 - b['avg_capture']) * 100:.0f}'ini geri veriyor"
                if b["avg_capture"] is not None
                else f"tepeden ort. %{b['avg_give_back_pct']:.2f} puan geri veriyor"
            )
            cards.append({
                "kind": "TRAILING_GIVEBACK", "timeframe": tf, "n": b["n"],
                "cost_usd_est": usd, "rank": rank,
                "label": f"{tf} iz-süren stop çıkışları {cap} — {_fmt_usd(usd)}",
            })
        elif cat == "sl" and b["sl_roundtrip"] > 0:
            usd = b["give_back_usd_est_total"]
            rank = usd if usd is not None else (b["avg_give_back_pct"] or 0.0) * b["sl_roundtrip"]
            cards.append({
                "kind": "SL_ROUNDTRIP", "timeframe": tf, "n": b["n"],
                "cost_usd_est": usd, "rank": rank,
                "label": (
                    f"{tf} stop'ları {b['sl_roundtrip']} kez ≥{ROUNDTRIP_MIN_R}R kârdayken "
                    f"ters dönüp zararla kapandı — {_fmt_usd(usd)}"
                ),
            })
        elif cat == "time_stop" and b["avg_missed_capture_pct"]:
            usd = b["missed_usd_est_total"]
            rank = usd if usd is not None else b["avg_missed_capture_pct"] * b["n"]
            cards.append({
                "kind": "TIMESTOP_MISSED", "timeframe": tf, "n": b["n"],
                "cost_usd_est": usd, "rank": rank,
                "label": (
                    f"{tf} süre-doluş çıkışları tepe kârın ort. "
                    f"%{b['avg_missed_capture_pct']:.2f} puanını bankaya koyamadı — {_fmt_usd(usd)}"
                ),
            })
    cards.sort(key=lambda c: c["rank"] or 0.0, reverse=True)
    for c in cards:
        c.pop("rank", None)
    return cards[:3]


def trainer_evidence(
    outcomes: list[CanonicalOutcome] | None = None, *, rep: dict | None = None
) -> dict[str, dict]:
    """TF-başı şiddet oranları (Dilim 5 girdisi). Veri yetersiz → {} (fake yok).

    - trailing_giveback_ratio: geri verilen / ort. tepe (trailing bucket)
    - sl_roundtrip_share: roundtrip / tüm SL (sl bucket)
    - timestop_missed_ratio: kaçan / ort. tepe (time_stop bucket)
    """
    r = rep if rep is not None else report(outcomes)
    by_tf: dict[str, dict] = {}
    for b in r["buckets"]:
        if b["n"] < MIN_BUCKET:
            continue
        tf = b["timeframe"]
        ev = by_tf.setdefault(tf, {"n": 0})
        ev["n"] += b["n"]
        if (
            b["category"] == "trailing"
            and b["avg_give_back_pct"] is not None
            and b["avg_mfe_pct"]
        ):
            ev["trailing_giveback_ratio"] = round(
                min(1.0, b["avg_give_back_pct"] / b["avg_mfe_pct"]), 4
            )
        elif b["category"] == "sl":
            sl_n = b["sl_roundtrip"] + b["sl_straight"] + b["sl_gray"]
            if sl_n:
                ev["sl_roundtrip_share"] = round(b["sl_roundtrip"] / sl_n, 4)
        elif (
            b["category"] == "time_stop"
            and b["avg_missed_capture_pct"] is not None
            and b["avg_mfe_pct"]
        ):
            ev["timestop_missed_ratio"] = round(
                min(1.0, b["avg_missed_capture_pct"] / b["avg_mfe_pct"]), 4
            )
    # Yalnız gerçekten oran taşıyan TF'ler (sadece n varsa kanıt yok demektir).
    return {tf: ev for tf, ev in by_tf.items() if len(ev) > 1}


def _total_bad_exit_cost(rep: dict) -> float | None:
    vals = [
        v
        for b in rep["buckets"]
        for v in (b["give_back_usd_est_total"], b["missed_usd_est_total"])
        if v is not None
    ]
    return round(sum(vals), 2) if vals else None


def write_snapshot(outcomes: list[CanonicalOutcome] | None = None) -> dict:
    """Rapor + trend geçmişi → data/runtime/exit_forensics.json (worker çağırır)."""
    rep = report(outcomes)
    path = snapshot_path()
    prev: dict = {}
    try:
        if path.exists():
            prev = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}  # bozuk/okunamayan snapshot → geçmiş sıfırdan (rapor bozulmaz)
    per_tf_capture = {
        b["timeframe"]: b["avg_capture"]
        for b in rep["buckets"]
        if b["category"] == "trailing" and b["avg_capture"] is not None
    }
    history = list(prev.get("history") or [])
    history.append({
        "generated_at": rep["generated_at"],
        "per_tf_capture": per_tf_capture,
        "total_bad_exit_cost_usd_est": _total_bad_exit_cost(rep),
    })
    payload = {"latest": rep, "history": history[-HISTORY_MAX:]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows: virüs tarayıcı/indexer dosyayı anlık kilitleyebilir → kısa retry
    # (worker asla patlamaz; son deneme başarısızsa exception yukarı çıkar,
    # run_once zaten try/except ile sarıyor).
    for attempt in range(3):
        try:
            tmp.replace(path)
            break
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)
    return payload
