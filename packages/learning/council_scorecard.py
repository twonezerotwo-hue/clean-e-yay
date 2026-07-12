"""Konsey karnesi — katmanlar-arası kombinasyon analizi (SALT-ANALİZ).

Owner isteği (2026-07-12): "23 katman birbirinden habersiz — hangileri birlikte
kullanılınca isabet/PnL artıyor?" Bu modül o analizi KALICI ve OTOMATİK yapar:
kapanmış işlemlerin karar bağlamını (modül katkıları, rejim, kalibre güven, TF)
sonuçla çaprazlar ve her koşuda YENİDEN keşfeder — bugünün bulgusu koda
gömülmez (aşırı-uyum tuzağı yok), veri değiştikçe tablo kendini günceller:

- **Modül yayılımı:** her modülün sesi güçlüyken (medyan-üstü katkı) vs
  zayıfken isabet/R farkı — hangi modül gerçek ayırıcı, hangisi ters gösterge.
- **İkili kombinasyonlar:** iki modül birden güçlüyken en iyi/en kötü çiftler.
- **Rejim ve güven-bandı kırılımları** (kalibrasyon + rejim katmanlarının
  kesişim karnesi).
- **Sanki-filtreler (what-if):** en kötü rejimi/en iyi modül-zayıfını/en kötü
  güven bandını kapıya koysaydık ne olurdu — filtreler VERİDEN türetilir,
  sabitlenmez. In-sample uyarısı artifact'ta taşınır.

Veri hijyeni içerde: `outcomes.learning_grade` (legacy kayıt giremez).
Config-flag YOK (zero_two_strategy deseni): salt-analiz, karara/paper'a
dokunmaz. Interval-kapılı (günlük). Kanıt: 2026-07-12 elle analizinde V6 üçlü
filtre isabeti %42.9→%52.2 taşımıştı — bu modül o analizin kalıcı hâlidir.
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

_ENGINE = "council_scorecard_v1"
_INTERVAL_ENV = "COUNCIL_SCORECARD_INTERVAL_SEC"
_DEFAULT_INTERVAL_SEC = 24 * 3600
_MIN_ROWS = 40          # altında konsey konuşmaz (uydurma yok)
_MIN_CELL = 15          # hücre/çift başına asgari örnek
_CONF_BANDS = ((0.0, 0.28), (0.28, 0.38), (0.38, 0.5), (0.5, 1.01))


def _path() -> Path:
    return Path(os.environ.get("COUNCIL_SCORECARD_PATH", "data/runtime/council_scorecard.json"))


def _interval_sec() -> int:
    try:
        return int(os.environ.get(_INTERVAL_ENV, str(_DEFAULT_INTERVAL_SEC)))
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


def _rows(outcomes) -> list[dict]:
    """Kapanmış + karar-bağlamı taşıyan işlemler → düz satırlar."""
    rows = []
    for o in outcomes:
        mc = dict(getattr(o, "module_contributions", None) or {})
        pnl = float(getattr(o, "pnl", 0.0) or 0.0)
        rows.append({
            "tf": str(o.timeframe or "?"),
            "regime": str(o.regime or "?"),
            "conf": getattr(o, "predicted_confidence", None),
            "mc": mc,
            "won": pnl > 0,
            "pnl": pnl,
            "r": getattr(o, "r_multiple", None),
        })
    return rows


def _stats(sub: list[dict]) -> dict:
    n = len(sub)
    if not n:
        return {"n": 0, "win_pct": None, "avg_r": None, "total_r": None, "total_pnl": 0.0}
    rs = [r["r"] for r in sub if r["r"] is not None]
    return {
        "n": n,
        "win_pct": round(sum(1 for r in sub if r["won"]) / n * 100, 1),
        "avg_r": round(statistics.mean(rs), 3) if rs else None,
        "total_r": round(sum(rs), 2) if rs else None,
        "total_pnl": round(sum(r["pnl"] for r in sub), 0),
    }


def module_spreads(rows: list[dict]) -> list[dict]:
    """Modül başına: sesi güçlüyken vs zayıfken fark (isabet-puan yayılımı)."""
    mods = sorted({m for r in rows for m in r["mc"]})
    out = []
    for m in mods:
        have = [r for r in rows if m in r["mc"]]
        if len(have) < 2 * _MIN_CELL:
            continue
        med = statistics.median(r["mc"][m] for r in have)
        hi = _stats([r for r in have if r["mc"][m] > med])
        lo = _stats([r for r in have if r["mc"][m] <= med])
        if not hi["n"] or not lo["n"]:
            continue
        out.append({
            "module": m, "median": round(med, 3),
            "strong": hi, "weak": lo,
            "win_spread": round((hi["win_pct"] or 0) - (lo["win_pct"] or 0), 1),
        })
    out.sort(key=lambda x: -x["win_spread"])
    return out


def pair_table(rows: list[dict], spreads: list[dict]) -> list[dict]:
    """İki modül birden güçlüyken (medyan-üstü) isabet — en iyi/en kötü çiftler."""
    med = {s["module"]: s["median"] for s in spreads}
    out = []
    for a, b in combinations(sorted(med), 2):
        sub = [r for r in rows
               if r["mc"].get(a, 0) > med[a] and r["mc"].get(b, 0) > med[b]]
        if len(sub) < _MIN_CELL:
            continue
        out.append({"pair": f"{a}+{b}", **_stats(sub)})
    out.sort(key=lambda x: -(x["win_pct"] or 0))
    return out


def regime_table(rows: list[dict]) -> list[dict]:
    return [
        {"regime": rg, **_stats([r for r in rows if r["regime"] == rg])}
        for rg in sorted({r["regime"] for r in rows})
    ]


def conf_band_table(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in _CONF_BANDS:
        sub = [r for r in rows if r["conf"] is not None and lo <= r["conf"] < hi]
        out.append({"band": f"{lo:.2f}-{min(hi, 1.0):.2f}", **_stats(sub)})
    return out


def what_if(rows: list[dict], spreads: list[dict],
            regimes: list[dict], bands: list[dict]) -> list[dict]:
    """Sanki-filtreler — kapı adayları VERİDEN türetilir (sabit kural gömülmez):
    en kötü rejim, en pozitif-yayılımlı modülün zayıf hali, en kötü güven bandı.
    Her filtre: kalan işlem + isabet + PnL (in-sample; kesin hüküm değil kanıt)."""
    base = _stats(rows)
    out = [{"filter": "taban (hepsi)", "kept_pct": 100, **base}]

    valid_rg = [g for g in regimes if g["n"] >= _MIN_CELL and g["regime"] != "?"]
    worst_rg = min(valid_rg, key=lambda g: g["total_r"] if g["total_r"] is not None else 0) if valid_rg else None
    if worst_rg:
        sub = [r for r in rows if r["regime"] != worst_rg["regime"]]
        out.append({"filter": f"{worst_rg['regime']} rejiminde açma",
                    "kept_pct": round(len(sub) / len(rows) * 100), **_stats(sub)})

    best_mod = next((s for s in spreads if s["win_spread"] > 0 and s["strong"]["n"] >= _MIN_CELL), None)
    if best_mod:
        m, md = best_mod["module"], best_mod["median"]
        sub = [r for r in rows if m not in r["mc"] or r["mc"].get(m, 0) > md]
        out.append({"filter": f"{m}-zayıfken açma",
                    "kept_pct": round(len(sub) / len(rows) * 100), **_stats(sub)})

    valid_b = [b for b in bands if b["n"] >= _MIN_CELL]
    worst_b = min(valid_b, key=lambda b: b["win_pct"] or 0) if valid_b else None
    if worst_b:
        lo, hi = (float(x) for x in worst_b["band"].split("-"))
        sub = [r for r in rows
               if not (r["conf"] is not None and lo <= r["conf"] < (hi + 0.01))]
        out.append({"filter": f"güven {worst_b['band']} bandında açma",
                    "kept_pct": round(len(sub) / len(rows) * 100), **_stats(sub)})

    # Hepsi birden (konsey oy birliği filtresi)
    sub = list(rows)
    if worst_rg:
        sub = [r for r in sub if r["regime"] != worst_rg["regime"]]
    if best_mod:
        m, md = best_mod["module"], best_mod["median"]
        sub = [r for r in sub if m not in r["mc"] or r["mc"].get(m, 0) > md]
    if worst_b:
        lo, hi = (float(x) for x in worst_b["band"].split("-"))
        sub = [r for r in sub
               if not (r["conf"] is not None and lo <= r["conf"] < (hi + 0.01))]
    out.append({"filter": "üçü birden (konsey filtresi)",
                "kept_pct": round(len(sub) / len(rows) * 100), **_stats(sub)})
    return out


def compute(now: datetime | None = None, outcomes=None) -> dict:
    """Konsey karnesini üret. Asla raise etmez (worker patlamaz)."""
    now = now or datetime.now(UTC)
    if outcomes is None:
        from packages.learning import outcomes as om
        outcomes = om.learning_grade(om.outcomes_from_state())
    rows = _rows(outcomes)
    if len(rows) < _MIN_ROWS:
        return {"generated_at": now.isoformat(), "engine": _ENGINE,
                "status": "INSUFFICIENT", "n": len(rows), "min_rows": _MIN_ROWS}
    spreads = module_spreads(rows)
    regimes = regime_table(rows)
    bands = conf_band_table(rows)
    pairs = pair_table(rows, spreads)
    return {
        "generated_at": now.isoformat(),
        "engine": _ENGINE,
        "status": "OK",
        "n": len(rows),
        "baseline": _stats(rows),
        "module_spreads": spreads,
        "pairs": pairs[:10],
        "regimes": regimes,
        "conf_bands": bands,
        "what_if": what_if(rows, spreads, regimes, bands),
        "note": (
            "SALT-ANALIZ + IN-SAMPLE: filtreler ayni veriden turetilip ayni "
            "veride olculur — kesin hukum degil KANIT. Karara baglanacak filtre "
            "once golge + ileri-veri ister. Veri hijyeni icerde (legacy haric)."
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

    Kendini-onarma: INSUFFICIENT artifact taze sayılmaz (ör. servis-restart
    anına denk gelen boş okuma) — hesap ucuz, sonraki döngü yeniden dener."""
    try:
        p = _path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            age = (datetime.now(UTC) - gen).total_seconds()
            if (data.get("engine") == _ENGINE and data.get("status") == "OK"
                    and 0 <= age < _interval_sec()):
                return {"status": "SKIP_FRESH", "age_sec": int(age)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    rep = compute()
    _write(rep)
    return {"status": rep.get("status", "OK"), "n": rep.get("n", 0)}


def viewmodel() -> dict:
    """GET /learning/council — konsey karnesi (read-only; panel HESAP YAPMAZ)."""
    try:
        p = _path()
        if not p.exists():
            return {"status": "NO_DATA", "generated_at": None}
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"status": "NO_DATA", "generated_at": None}
    return {**data, "shadow_only": True}


__all__ = [
    "compute",
    "conf_band_table",
    "module_spreads",
    "pair_table",
    "regime_table",
    "run_if_due",
    "viewmodel",
    "what_if",
]
